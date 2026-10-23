"""Read tools for meetings: the next calendar event with its attendees, open items and recent decisions."""
import json

from datetime import date, timedelta

from .memory_views import open_items_as_of, recent_decisions_as_of
from .people_directory import INTERNAL_AREA
from .tool_reply import ToolInputError, build_tool, client_area_ids, int_arg, next_day, str_arg


def _event_area(row):
    return row["client_id"] or INTERNAL_AREA


def make_upcoming_meeting(data_conn):
    def handler(args, area_id, as_of, ctx):
        event_id = str_arg(args, "event_id") or ctx.task.inputs.get("event_id")
        if event_id:
            rows = data_conn.execute("SELECT * FROM calendar_events WHERE event_id = ?", (event_id,)).fetchall()
            if not rows or _event_area(rows[0]) != area_id:
                raise ToolInputError(f"event {event_id!r} is not in area {area_id!r}")
        else:
            until = next_day(_plus(as_of, int_arg(args, "days", 14, 1, 60)))
            rows = data_conn.execute(
                "SELECT * FROM calendar_events WHERE COALESCE(client_id, ?) = ? AND start_at >= ? AND start_at < ? "
                "ORDER BY start_at LIMIT 5", (INTERNAL_AREA, area_id, as_of, until)).fetchall()
        return {"as_of": as_of, "events": [_event(data_conn, r) for r in rows]}
    return build_tool(
        "upcoming_meeting",
        "A calendar event (by event_id, else the next ones within `days`) with title, time, project and attendees "
        "(name, role, DevX or client).",
        {"event_id": {"type": "string"}, "days": {"type": "integer"}}, handler,
        area_ok=lambda a: a in client_area_ids(data_conn) or a == INTERNAL_AREA, area_label="a client area or devx-internal")


def _plus(day, n):
    return (date.fromisoformat(day) + timedelta(days=n)).isoformat()


def _event(conn, r):
    people = []
    for pid in json.loads(r["attendees"] or "[]"):
        p = conn.execute("SELECT person_id, name, role, is_devx FROM people WHERE person_id = ?", (pid,)).fetchone()
        people.append({"person_id": pid, "name": p["name"], "role": p["role"], "is_devx": bool(p["is_devx"])}
                      if p else {"person_id": pid})
    project = conn.execute("SELECT name FROM projects WHERE project_id = ?", (r["project_id"],)).fetchone()
    return {"event_id": r["event_id"], "title": r["title"], "start_at": r["start_at"], "project_id": r["project_id"],
            "project_name": project["name"] if project else None, "attendees": people}


def _meeting_projects(data_conn):
    return {r["meeting_id"]: r["project_id"] for r in data_conn.execute("SELECT meeting_id, project_id FROM meetings")}


def _view(item, projects):
    meeting_id = (item["source"] or "").removeprefix("meeting:")
    return {"item_id": item["item_id"], "kind": item["kind"], "text": item["text"], "topic": item["topic"],
            "owner_id": item["owner_id"], "created_at": item["created_at"], "meeting_id": meeting_id,
            "project_id": projects.get(meeting_id), **({"answers": item["answers"]} if "answers" in item else {})}


def _scoped(memory, ctx, area_id):
    return memory.scoped([area_id]) if memory is not None else ctx.memory


def make_project_open_items(data_conn, memory=None):
    def handler(args, area_id, as_of, ctx):
        project_id, projects = str_arg(args, "project_id"), _meeting_projects(data_conn)
        items = open_items_as_of(_scoped(memory, ctx, area_id), area_id, next_day(as_of))
        rows = [_view(i, projects) for i in items]
        if project_id:
            rows = [r for r in rows if r["project_id"] == project_id]
        limit = int_arg(args, "limit", 25, 1, 150)
        return {"as_of": as_of, "count": len(rows), "items": rows[-limit:]}
    return build_tool(
        "project_open_items",
        "Open questions and tasks from meetings as of the date: not answered or superseded by then. Optional project_id.",
        {"project_id": {"type": "string"}, "limit": {"type": "integer"}}, handler,
        area_ok=lambda a: a in client_area_ids(data_conn) or a == INTERNAL_AREA,
        area_label="a client area or devx-internal", reads_outside_text=True)


def make_project_recent_decisions(data_conn, memory=None):
    def handler(args, area_id, as_of, ctx):
        project_id, projects = str_arg(args, "project_id"), _meeting_projects(data_conn)
        days = int_arg(args, "days", 30, 1, 365)
        items = recent_decisions_as_of(_scoped(memory, ctx, area_id), area_id, next_day(as_of), days=days)
        rows = [_view(i, projects) for i in items]
        if project_id:
            rows = [r for r in rows if r["project_id"] == project_id]
        return {"as_of": as_of, "days": days, "count": len(rows), "decisions": rows[-int_arg(args, "limit", 20, 1, 100):]}
    return build_tool(
        "project_recent_decisions",
        "Decisions from meetings in the last `days` as of the date, with the question ids they answer. Optional project_id.",
        {"project_id": {"type": "string"}, "days": {"type": "integer"}, "limit": {"type": "integer"}}, handler,
        area_ok=lambda a: a in client_area_ids(data_conn) or a == INTERNAL_AREA,
        area_label="a client area or devx-internal", reads_outside_text=True)


def meeting_tools(data_conn, memory=None):
    return [make_upcoming_meeting(data_conn), make_project_open_items(data_conn, memory),
            make_project_recent_decisions(data_conn, memory)]
