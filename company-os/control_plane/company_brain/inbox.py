"""Inbox: take one file of any kind, read it, find its client area and store it as a source."""
import hashlib
import json

from .area_router import devx_domains, route, title_names_client
from .language import detect_language
from .source_readers import read_chat, read_docx, read_eml, read_fathom_json, read_plain

KINDS = ("fathom", "docx", "email", "chat", "plain")


def _read(kind, content):
    """Return (meta, lines, raw_text). raw_text of a binary file is its lines joined."""
    if kind == "docx":
        meta, lines = read_docx(content)
        return meta, lines, "\n".join(line["text"] for line in lines)
    if kind == "email":
        meta, lines = read_eml(content if isinstance(content, bytes) else content.encode("utf-8"))
        return meta, lines, "\n".join(line["text"] for line in lines)
    reader = {"fathom": read_fathom_json, "chat": read_chat, "plain": read_plain}.get(kind)
    if reader is None:
        raise ValueError(f"unknown source kind {kind!r}")
    text = content.decode("utf-8") if isinstance(content, bytes) else content
    meta, lines = reader(text)
    return meta, lines, text


def should_ingest(meeting, data_conn=None):
    """Decide if a Fathom meeting goes into the brain: (True or False, plain reason).

    Yes for an external attendee, for a title that names a client, prospect or project, or for "#brain" in the title.
    """
    if isinstance(meeting, str):
        meeting = json.loads(meeting)
    internal = devx_domains(data_conn) if data_conn is not None else set()
    internal |= {"devx-demo.example", "devxlabs.ai"}
    addresses = [p.get("email") or "" for p in meeting.get("calendar_invitees", [])]
    addresses += [((seg.get("speaker") or {}).get("matched_calendar_invitee_email") or "") for seg in meeting.get("transcript", [])]
    if any("@" in a and a.rsplit("@", 1)[-1].strip().lower() not in internal for a in addresses):
        return True, "an attendee is outside the company"
    title = meeting.get("title") or ""
    if data_conn is not None and title_names_client(data_conn, title):
        return True, "the title names a client, prospect or project"
    if "#brain" in title.lower():
        return True, "the title has #brain"
    return False, "internal meeting without #brain"


def receive(brain, data_conn, *, kind, content, filename=None, received_at=None, hint_area=None, origin_ref=None,
            submitted_by=None, force=False):
    """Store one source. Same origin_ref again returns the stored one with "duplicate": True.

    A Fathom meeting that should_ingest refuses is skipped (source_id None, "skipped": reason) unless force or hint_area is set.
    """
    if kind == "fathom" and not force and not hint_area:
        ok, why = should_ingest(content, data_conn)
        if not ok:
            return {"source_id": None, "area_id": None, "routed_by": "skipped", "lines": 0, "language": None, "skipped": why}
    meta, lines, raw = _read(kind, content)
    origin_ref = origin_ref or meta.get("origin_ref") or "IN-" + hashlib.sha1(
        content if isinstance(content, bytes) else content.encode("utf-8")).hexdigest()[:10]
    old = brain.source_by_ref(origin_ref)
    if old is not None:
        return {"source_id": old["source_id"], "area_id": old["area_id"], "routed_by": "duplicate",
                "lines": len(brain.source_lines(old["source_id"])), "language": old["language"], "duplicate": True}
    if not lines:
        raise ValueError("the file has no text lines")
    area_id, routed_by = route(data_conn, meta["participants"], meta["title"], hint_area)
    language = detect_language(" ".join(line["text"] for line in lines))
    source_id = brain.add_source(
        area_id, kind, meta["title"] or filename or origin_ref, raw, origin_ref=origin_ref, occurred_at=meta["occurred_at"],
        participants=meta["participants"], language=language, lines=lines, received_at=received_at,
        submitted_by=submitted_by)
    return {"source_id": source_id, "area_id": area_id, "routed_by": routed_by, "lines": len(lines), "language": language}
