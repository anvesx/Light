"""Loads meetings, items, links and transcripts from company data into company memory."""
import json

from .people_directory import HOLD_AREA, INTERNAL_AREA


def meeting_area(meeting, known_clients):
    if meeting["client_id"] in known_clients:
        return meeting["client_id"]
    if meeting["client_id"] is None and meeting["kind"] == "internal":
        return INTERNAL_AREA
    return HOLD_AREA


def _has_link(memory, from_id, rel, to_id):
    return any(l["from_id"] == from_id and l["rel"] == rel and l["to_id"] == to_id for l in memory.links_of(from_id))


def sync_meetings(data_conn, memory, until=None) -> dict:
    """Copy meetings into memory. Safe to run twice. Meetings at or after `until` are skipped."""
    clients = {r["client_id"]: r["name"] for r in data_conn.execute("SELECT client_id, name FROM clients")}
    counts = {"meetings": 0, "items_added": 0, "transcripts_added": 0, "links_added": 0, "links_skipped": 0}
    sql = "SELECT * FROM meetings" + (" WHERE start_at < ?" if until else "") + " ORDER BY start_at, meeting_id"
    meetings = data_conn.execute(sql, (until,) if until else ()).fetchall()
    placed = {}   # item_id -> (area_id, start_at)
    for m in meetings:
        area = meeting_area(m, clients)
        memory.ensure_area(area, name=clients.get(area))
        counts["meetings"] += 1
        source = f"meeting:{m['meeting_id']}"
        if m["transcript"]:
            tid = f"TR-{m['meeting_id']}"
            fresh = memory.get_item(tid) is None
            memory.add_item(area, "transcript", m["transcript"], topic=None, status="noted", source=source,
                            source_ref=m["meeting_id"], created_at=m["start_at"], item_id=tid)
            counts["transcripts_added"] += fresh
        for it in data_conn.execute("SELECT * FROM meeting_items WHERE meeting_id = ? ORDER BY item_id",
                                    (m["meeting_id"],)):
            fresh = memory.get_item(it["item_id"]) is None
            memory.add_item(area, it["kind"], it["text"], topic=it["topic"], status=it["status"], source=source,
                            source_ref=it["item_id"], created_at=m["start_at"], owner_id=it["owner_id"],
                            item_id=it["item_id"])
            counts["items_added"] += fresh
            placed[it["item_id"]] = (area, m["start_at"])
    _add_links(data_conn, memory, placed, counts)
    return counts


def _add_links(data_conn, memory, placed, counts):
    rows = data_conn.execute(
        "SELECT item_id, answers_item_id, supersedes_item_id FROM meeting_items "
        "WHERE answers_item_id IS NOT NULL OR supersedes_item_id IS NOT NULL ORDER BY item_id")
    for r in rows:
        if r["item_id"] not in placed:
            continue
        area, at = placed[r["item_id"]]   # the link is made when the later meeting happens
        for rel, target in (("answers", r["answers_item_id"]), ("supersedes", r["supersedes_item_id"])):
            if target is None:
                continue
            tgt = memory.get_item(target)
            if tgt is None or tgt["area_id"] != area:
                counts["links_skipped"] += 1
                continue
            if not _has_link(memory, r["item_id"], rel, target):
                memory.add_link(r["item_id"], rel, target, created_at=at)
                counts["links_added"] += 1
