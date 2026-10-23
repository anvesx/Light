"""Read tools for git delivery data: SOW scope burn-down, merged PRs with no task, and project pace."""
import json
from datetime import date, timedelta

from .tool_reply import ToolInputError, build_tool, client_area_ids, int_arg, monday_of, str_arg

AREA_LABEL = "a client area"
CHORE_MAX_LINES = 30


def _day(stamp):
    return stamp[:10] if stamp else None


def _merged(pr, as_of):
    return bool(pr["merged_at"]) and _day(pr["merged_at"]) <= as_of


def _projects(conn, area_id, as_of, project_id=None, active_only=False):
    sql, params = "SELECT * FROM projects WHERE client_id = ? AND start_on <= ?", [area_id, as_of]
    if project_id:
        sql, params = sql + " AND project_id = ?", params + [project_id]
    if active_only:
        sql += " AND status = 'active'"
    return conn.execute(sql + " ORDER BY project_id", params).fetchall()


def _check_project(conn, area_id, project_id):
    row = conn.execute("SELECT client_id FROM projects WHERE project_id = ?", (project_id,)).fetchone()
    if row is None or row["client_id"] != area_id:
        raise ToolInputError(f"project {project_id!r} is not in area {area_id!r}")


def _production_prs(conn, project_id, as_of):
    out = set()
    for r in conn.execute("SELECT deployed_at, pr_ids FROM deploys WHERE project_id = ? AND env = 'production'",
                          (project_id,)):
        if _day(r["deployed_at"]) <= as_of:
            out.update(json.loads(r["pr_ids"]))
    return out


def _scope_rows(conn, p, as_of):
    pid = p["project_id"]
    tasks = {r["task_id"]: r for r in conn.execute("SELECT * FROM tasks WHERE project_id = ?", (pid,))}
    item_of = {r["task_id"]: r["scope_item_id"] for r in conn.execute(
        "SELECT s.task_id, s.scope_item_id FROM task_scope s JOIN scope_items i ON i.scope_item_id = s.scope_item_id "
        "WHERE i.project_id = ?", (pid,))}
    prs = [r for r in conn.execute("SELECT * FROM pull_requests WHERE project_id = ?", (pid,))
           if _day(r["opened_at"]) <= as_of]
    in_prod = _production_prs(conn, pid, as_of)
    rows = []
    for it in conn.execute("SELECT * FROM scope_items WHERE project_id = ? ORDER BY scope_item_id", (pid,)):
        ids = [t for t, i in item_of.items() if i == it["scope_item_id"]]
        done = sum(1 for t in ids if tasks[t]["done_on"] and tasks[t]["done_on"] <= as_of)
        mine = [r for r in prs if r["task_id"] in ids]
        merged = [r for r in mine if _merged(r, as_of)]
        rows.append({"id": it["scope_item_id"], "title": it["title"], "est": it["estimate_hours"],
                     "due_on": it["due_on"], "tasks_done": done, "tasks_open": len(ids) - done,
                     "prs_merged": len(merged), "prs_open": len(mine) - len(merged),
                     "last_merge": max((_day(r["merged_at"]) for r in merged), default=None),
                     "in_prod": bool(merged) and all(r["pr_id"] in in_prod for r in merged),
                     "revisions": sum(1 for r in mine if r["after_meeting_id"])})
    return rows


def make_scope_burndown(data_conn):
    def handler(args, area_id, as_of, ctx):
        project_id, pr_id = str_arg(args, "project_id"), str_arg(args, "pr_id")
        if project_id:
            _check_project(data_conn, area_id, project_id)
        out = {"as_of": as_of, "projects": [
            {"project_id": p["project_id"], "name": p["name"], "scope": _scope_rows(data_conn, p, as_of)}
            for p in _projects(data_conn, area_id, as_of, project_id)]}
        if pr_id:
            out["trigger_pr"] = _trigger_pr(data_conn, area_id, pr_id)
        return out
    return build_tool(
        "scope_burndown",
        "Per project and SOW scope item as of the date: estimate hours, linked tasks done and open, merged and open "
        "PRs, last merge date, deployed to production, revisions after client meetings. Optional pr_id adds that PR's "
        "project and scope item. No people are named.",
        {"project_id": {"type": "string"}, "pr_id": {"type": "string"}}, handler,
        area_ok=lambda a: a in client_area_ids(data_conn), area_label=AREA_LABEL)


def _trigger_pr(conn, area_id, pr_id):
    row = conn.execute(
        "SELECT r.pr_id, r.project_id, r.task_id, r.merged_at, p.client_id FROM pull_requests r "
        "JOIN projects p ON p.project_id = r.project_id WHERE r.pr_id = ?", (pr_id,)).fetchone()
    if row is None or row["client_id"] != area_id:
        raise ToolInputError(f"PR {pr_id!r} is not in area {area_id!r}")
    item = conn.execute("SELECT scope_item_id FROM task_scope WHERE task_id = ?", (row["task_id"],)).fetchone()
    return {"pr_id": pr_id, "project_id": row["project_id"], "scope_item_id": item[0] if item else None,
            "merged_at": _day(row["merged_at"])}


def make_unlinked_merged_prs(data_conn):
    def handler(args, area_id, as_of, ctx):
        project_id = str_arg(args, "project_id")
        if project_id:
            _check_project(data_conn, area_id, project_id)
        limit = int_arg(args, "limit", 40, 1, 100)
        rows, by_project = [], {}
        for p in _projects(data_conn, area_id, as_of, project_id):
            for r in data_conn.execute("SELECT * FROM pull_requests WHERE project_id = ? AND task_id IS NULL "
                                       "ORDER BY merged_at, pr_id", (p["project_id"],)):
                if not _merged(r, as_of):
                    continue
                chore = r["lines_changed"] < CHORE_MAX_LINES or r["title"].lower().startswith("chore")
                rows.append({"pr_id": r["pr_id"], "project_id": r["project_id"], "title": r["title"],
                             "lines": r["lines_changed"], "merged_on": _day(r["merged_at"]), "chore": chore})
                stat = by_project.setdefault(p["project_id"], {"merged_unlinked": 0, "not_chore": 0})
                stat["merged_unlinked"] += 1
                stat["not_chore"] += 0 if chore else 1
        return {"as_of": as_of, "by_project": by_project, "count": len(rows), "prs": rows[:limit]}
    return build_tool(
        "unlinked_merged_prs",
        "Merged PRs that link to no task or scope item, with title and lines. Small chores (under 30 lines or titled "
        "chore) are marked. No people are named.",
        {"project_id": {"type": "string"}, "limit": {"type": "integer"}}, handler,
        area_ok=lambda a: a in client_area_ids(data_conn), area_label=AREA_LABEL)


def make_project_pace(data_conn):
    def handler(args, area_id, as_of, ctx):
        project_id = str_arg(args, "project_id")
        if project_id:
            _check_project(data_conn, area_id, project_id)
        return {"as_of": as_of, "projects": [_pace(data_conn, p, as_of)
                                              for p in _projects(data_conn, area_id, as_of, project_id, True)]}
    return build_tool(
        "project_pace",
        "Per active project: share of the calendar used against share of linked scope hours merged, measured on the "
        "latest Monday, with the finish date at that pace and the planned end.",
        {"project_id": {"type": "string"}}, handler,
        area_ok=lambda a: a in client_area_ids(data_conn), area_label=AREA_LABEL)


def _pace(conn, p, as_of):
    pid = p["project_id"]
    start, end = date.fromisoformat(p["start_on"]), date.fromisoformat(p["planned_end_on"])
    pace_day = max(date.fromisoformat(monday_of(as_of)), start)
    hours = {r["task_id"]: r["estimate_hours"] for r in conn.execute(
        "SELECT k.task_id, k.estimate_hours FROM task_scope s JOIN tasks k ON k.task_id = s.task_id "
        "WHERE k.project_id = ?", (pid,))}
    merged_tasks = {r["task_id"] for r in conn.execute(
        "SELECT task_id, merged_at FROM pull_requests WHERE project_id = ? AND task_id IS NOT NULL "
        "AND merged_at IS NOT NULL", (pid,)) if _day(r["merged_at"]) <= pace_day.isoformat()}
    total = sum(hours.values())
    done = sum(h for t, h in hours.items() if t in merged_tasks)
    elapsed = (pace_day - start).days / max(1, (end - start).days)
    share = done / total if total else 0.0
    projected = None
    if share > 0 and pace_day > start:
        projected = (start + timedelta(days=round((pace_day - start).days / share))).isoformat()
    late = (date.fromisoformat(projected) - end).days if projected else None
    return {"project_id": pid, "name": p["name"], "csm_id": p["csm_id"], "lead_id": p["lead_id"],
            "start_on": p["start_on"], "planned_end_on": p["planned_end_on"], "pace_date": pace_day.isoformat(),
            "elapsed_share": round(elapsed, 4), "linked_hours": total, "merged_hours": done,
            "merged_share": round(share, 4), "projected_finish": projected, "days_late": late}


def git_tools(data_conn):
    return [make_scope_burndown(data_conn), make_unlinked_merged_prs(data_conn), make_project_pace(data_conn)]
