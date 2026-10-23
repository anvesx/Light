"""Read tools for hiring: team capacity against load, sales pipeline demand, remaining SOW hours."""
from datetime import date, timedelta

from .project_hours import project_stats
from .tool_reply import build_tool, int_arg, monday_of

AREA = "devx-internal"
WEEK_HOURS = 40
KICKOFF_DAYS = {"won": 14, "proposal": 45}   # assumed days from win (or lead creation) to project start


def _ok(area_id):
    return area_id == AREA


def make_team_capacity_and_load(data_conn):
    def handler(args, area_id, as_of, ctx):
        weeks = int_arg(args, "weeks", 6, 1, 26)
        last = date.fromisoformat(monday_of(as_of))
        starts = [(last - timedelta(weeks=i)).isoformat() for i in range(weeks - 1, -1, -1)]
        teams = {r["team"]: r["n"] for r in data_conn.execute(
            "SELECT team, COUNT(*) AS n FROM people WHERE is_devx = 1 AND team IN "
            "(SELECT DISTINCT p.team FROM time_logs l JOIN people p ON p.person_id = l.person_id) GROUP BY team")}
        logged = {}
        for r in data_conn.execute(
                "SELECT p.team, l.date, l.hours FROM time_logs l JOIN people p ON p.person_id = l.person_id "
                "WHERE l.date >= ? AND l.date <= ?", (starts[0], as_of)):
            key = (r["team"], monday_of(r["date"]))
            logged[key] = logged.get(key, 0) + r["hours"]
        rows = []
        for team, n in sorted(teams.items()):
            cap = n * WEEK_HOURS
            rows.append({"team": team, "people": n, "capacity_hours_per_week": cap, "weeks": [
                {"week_start": w, "hours": round(logged.get((team, w), 0), 1),
                 "load_pct": round(100 * logged.get((team, w), 0) / cap, 1),
                 "week_complete": (date.fromisoformat(w) + timedelta(days=6)).isoformat() <= as_of} for w in starts]})
        return {"as_of": as_of, "note": "capacity = people x 40 hours; load = logged hours / capacity", "teams": rows}
    return build_tool(
        "team_capacity_and_load", "Per team: people, weekly capacity (people x 40) and weekly logged hours with load percent "
        "for the last `weeks` (default 6).", {"weeks": {"type": "integer"}}, handler, area_ok=_ok, area_label=AREA)


def make_pipeline_demand(data_conn):
    def handler(args, area_id, as_of, ctx):
        rate = data_conn.execute("SELECT SUM(price_inr) * 1.0 / SUM(estimate_hours) FROM sows WHERE status = 'signed'").fetchone()[0]
        rows = []
        for r in data_conn.execute("SELECT * FROM leads WHERE created_on <= ? AND stage != 'lost' ORDER BY lead_id", (as_of,)):
            won = bool(r["won_on"]) and r["won_on"] <= as_of
            stage = "won" if won else ("proposal" if r["stage"] == "won" else r["stage"])
            if stage not in KICKOFF_DAYS:
                continue
            base = r["won_on"] if won else r["created_on"]
            start = (date.fromisoformat(base) + timedelta(days=KICKOFF_DAYS[stage])).isoformat()
            rows.append({"lead_id": r["lead_id"], "client_id": r["client_id"], "stage": stage, "source": r["source"],
                         "value_inr": r["value_inr"], "approx_hours": round(r["value_inr"] / rate),
                         "expected_start": start, "started": start <= as_of})
        return {"as_of": as_of, "note": "expected_start is assumed: won + 14 days, proposal stage lead created + 45 days; "
                                         "approx_hours = value / average signed rate", "leads": rows}
    return build_tool(
        "pipeline_demand", "Won and proposal-stage leads with value, approximate hours and an assumed expected start.",
        {}, handler, area_ok=_ok, area_label=AREA)


def make_remaining_sow_hours(data_conn):
    def handler(args, area_id, as_of, ctx):
        rows = []
        for p in project_stats(data_conn, as_of):
            if not (p["status"] == "active" or as_of <= p["planned_end_on"]) or p["estimate_hours_with_changes"] is None:
                continue
            by_team = {r["team"]: round(r["h"], 1) for r in data_conn.execute(
                "SELECT pe.team, SUM(k.estimate_hours) AS h FROM tasks k JOIN people pe ON pe.person_id = k.assignee_id "
                "WHERE k.project_id = ? AND (k.done_on IS NULL OR k.done_on > ?) GROUP BY pe.team", (p["project_id"], as_of))}
            remaining = max(p["estimate_hours_with_changes"] - p["hours_logged"], 0)
            rows.append({"project_id": p["project_id"], "client_id": p["client_id"], "name": p["name"], "status": p["status"],
                         "planned_end_on": p["planned_end_on"], "estimate_hours_with_changes": p["estimate_hours_with_changes"],
                         "hours_logged": p["hours_logged"], "remaining_hours": round(remaining, 1),
                         "open_task_estimate_by_team": by_team})
        return {"as_of": as_of, "projects": rows}
    return build_tool(
        "remaining_sow_hours", "Per active project: signed estimate plus accepted changes, hours logged, remaining hours, "
        "planned end and open task estimate hours by team.", {}, handler, area_ok=_ok, area_label=AREA)


def staffing_tools(data_conn):
    return [make_team_capacity_and_load(data_conn), make_pipeline_demand(data_conn), make_remaining_sow_hours(data_conn)]
