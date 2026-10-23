"""Read tools for delivery data: projects against their SOWs, tasks, and weekly hours per person."""
from datetime import date, timedelta

from .project_hours import project_stats
from .tool_reply import ToolInputError, build_tool, client_area_ids, monday_of, int_arg, str_arg

AREA_LABEL = "a client area"


def _check_project(conn, area_id, project_id):
    row = conn.execute("SELECT client_id FROM projects WHERE project_id = ?", (project_id,)).fetchone()
    if row is None or row["client_id"] != area_id:
        raise ToolInputError(f"project {project_id!r} is not in area {area_id!r}")


def make_project_overview(data_conn):
    def handler(args, area_id, as_of, ctx):
        return {"as_of": as_of, "projects": project_stats(data_conn, as_of, area_id)}
    return build_tool(
        "project_overview",
        "Projects of the area: signed SOW estimate, accepted and unaccepted change hours, hours logged to date, "
        "open and overdue task counts, lead and CSM.", {}, handler,
        area_ok=lambda a: a in client_area_ids(data_conn), area_label=AREA_LABEL)


def make_project_tasks(data_conn):
    def handler(args, area_id, as_of, ctx):
        project_id, state = str_arg(args, "project_id"), args.get("state", "open")
        if state not in ("open", "overdue", "all"):
            raise ToolInputError("state must be open, overdue or all")
        if project_id:
            _check_project(data_conn, area_id, project_id)
        limit = int_arg(args, "limit", 60, 1, 200)
        sql = ("SELECT k.task_id, k.project_id, k.title, k.assignee_id, k.estimate_hours, k.due_on, k.done_on, "
               "COALESCE((SELECT SUM(hours) FROM time_logs l WHERE l.task_id = k.task_id AND l.date <= ?), 0) AS logged "
               "FROM tasks k JOIN projects p ON p.project_id = k.project_id "
               "WHERE p.client_id = ? AND p.start_on <= ?")
        params = [as_of, area_id, as_of]
        if project_id:
            sql += " AND k.project_id = ?"
            params.append(project_id)
        rows = data_conn.execute(sql + " ORDER BY k.due_on, k.task_id", params).fetchall()
        out = []
        for r in rows:
            is_open = r["done_on"] is None or r["done_on"] > as_of
            overdue = is_open and r["due_on"] is not None and r["due_on"] < as_of
            if (state == "open" and not is_open) or (state == "overdue" and not overdue):
                continue
            out.append({"task_id": r["task_id"], "project_id": r["project_id"], "title": r["title"],
                        "assignee_id": r["assignee_id"], "estimate_hours": r["estimate_hours"],
                        "hours_logged": round(r["logged"], 1), "due_on": r["due_on"],
                        "state": "overdue" if overdue else ("open" if is_open else "done")})
        return {"as_of": as_of, "count": len(out), "tasks": out[:limit]}
    return build_tool(
        "project_tasks", "Tasks with state as of the date (open, overdue or done) and hours logged to date.",
        {"project_id": {"type": "string"}, "state": {"type": "string", "enum": ["open", "overdue", "all"]},
         "limit": {"type": "integer"}}, handler,
        area_ok=lambda a: a in client_area_ids(data_conn), area_label=AREA_LABEL)


def make_weekly_hours_by_person(data_conn):
    def handler(args, area_id, as_of, ctx):
        weeks = int_arg(args, "weeks", 4, 1, 12)
        project_id = str_arg(args, "project_id")
        if project_id:
            _check_project(data_conn, area_id, project_id)
        first = monday_of(as_of)
        start = (date.fromisoformat(first) - timedelta(weeks=weeks - 1)).isoformat()
        sql = ("SELECT l.person_id, l.date, l.hours FROM time_logs l JOIN tasks k ON k.task_id = l.task_id "
               "JOIN projects p ON p.project_id = k.project_id WHERE p.client_id = ? AND l.date >= ? AND l.date <= ?")
        params = [area_id, start, as_of]
        if project_id:
            sql += " AND k.project_id = ?"
            params.append(project_id)
        totals = {}
        for r in data_conn.execute(sql, params):
            key = (r["person_id"], monday_of(r["date"]))
            totals[key] = totals.get(key, 0) + r["hours"]
        rows = [{"person_id": p, "week_start": w, "hours": round(h, 1),
                 "week_complete": _sunday(w) <= as_of} for (p, w), h in sorted(totals.items())]
        return {"as_of": as_of, "weeks": weeks, "note": "weeks run Monday to Sunday; hours in this area only", "rows": rows}
    return build_tool(
        "weekly_hours_by_person", "Hours logged per person per Monday-to-Sunday week on the area's projects.",
        {"weeks": {"type": "integer"}, "project_id": {"type": "string"}}, handler,
        area_ok=lambda a: a in client_area_ids(data_conn), area_label=AREA_LABEL)


def _sunday(monday):
    return (date.fromisoformat(monday) + timedelta(days=6)).isoformat()


def project_tools(data_conn):
    return [make_project_overview(data_conn), make_project_tasks(data_conn), make_weekly_hours_by_person(data_conn)]
