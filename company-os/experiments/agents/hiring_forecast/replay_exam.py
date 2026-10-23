"""Exam for the hiring forecast agent. The answer key is derived from the raw tables by a separate, simple calculation.

No answer key is planted for this agent. The key below does not use the pack or the connector tools.
"""
import json
import math
from datetime import date, timedelta

from company_data.simulated_today import TODAY

# Same stated assumptions as the pack. They are repeated here on purpose, so the key stands alone.
PERSON_HOURS, HIRING_LEAD_WEEKS, HORIZON, PROPOSAL_WEIGHT, BUILD_WEEKS, SPARE_PCT = 32.0, 4, 8, 0.5, 12, 15
KICKOFF_DAYS = {"won": 14, "proposal": 45}
TOLERANCE_HOURS = 1.0


def derive_key(conn, as_of=TODAY) -> dict:
    """Short and spare teams for the next weeks, straight from people, sows, projects, tasks, time_logs and leads."""
    today = date.fromisoformat(as_of)
    mondays = [today + timedelta(days=(7 - today.weekday()) % 7 + 7 * k) for k in range(HORIZON)]
    teams = [r[0] for r in conn.execute(
        "SELECT DISTINCT p.team FROM time_logs l JOIN people p ON p.person_id = l.person_id ORDER BY 1")]
    heads = {t: conn.execute("SELECT COUNT(*) FROM people WHERE is_devx = 1 AND team = ?", (t,)).fetchone()[0] for t in teams}
    demand = {t: [0.0] * HORIZON for t in teams}
    signed = dict.fromkeys(teams, 0.0)
    for pr in conn.execute("SELECT * FROM projects WHERE status = 'active' AND start_on <= ?", (as_of,)).fetchall():
        sow = conn.execute("SELECT estimate_hours FROM sows WHERE sow_id = ? AND signed_on <= ?", (pr["sow_id"], as_of)).fetchone()
        if sow is None:
            continue
        extra = conn.execute("SELECT COALESCE(SUM(hours_delta), 0) FROM sow_changes WHERE sow_id = ? AND accepted = 1 "
                             "AND date <= ?", (pr["sow_id"], as_of)).fetchone()[0]
        logged = conn.execute("SELECT COALESCE(SUM(l.hours), 0) FROM time_logs l JOIN tasks k ON k.task_id = l.task_id "
                              "WHERE k.project_id = ? AND l.date <= ?", (pr["project_id"], as_of)).fetchone()[0]
        left = max(sow[0] + extra - logged, 0)
        open_est = {r[0]: r[1] for r in conn.execute(
            "SELECT pe.team, SUM(k.estimate_hours) FROM tasks k JOIN people pe ON pe.person_id = k.assignee_id "
            "WHERE k.project_id = ? AND (k.done_on IS NULL OR k.done_on > ?) GROUP BY pe.team", (pr["project_id"], as_of))}
        open_est = {t: h for t, h in open_est.items() if t in teams}
        if left <= 0 or not open_est:
            continue
        end = max(date.fromisoformat(pr["planned_end_on"]), today + timedelta(days=7))
        n_weeks = math.ceil((end - today).days / 7)
        for t, h in open_est.items():
            part = left * h / sum(open_est.values())
            signed[t] += part
            for k, m in enumerate(mondays):
                if m <= end:
                    demand[t][k] += part / n_weeks
    rate = conn.execute("SELECT SUM(price_inr) * 1.0 / SUM(estimate_hours) FROM sows WHERE status = 'signed'").fetchone()[0]
    for lead in conn.execute("SELECT * FROM leads WHERE created_on <= ? AND stage != 'lost'", (as_of,)):
        won = lead["won_on"] is not None and lead["won_on"] <= as_of
        kind = "won" if won else ("proposal" if lead["stage"] in ("proposal", "won") else None)
        if kind is None:
            continue
        base = lead["won_on"] if won else lead["created_on"]
        start = date.fromisoformat(base) + timedelta(days=KICKOFF_DAYS[kind])
        if start <= today:
            continue                      # already running: its hours are in the signed projects
        hours = round(lead["value_inr"] / rate) * (1.0 if won else PROPOSAL_WEIGHT)
        first = start - timedelta(days=start.weekday())
        for t in teams:
            for k, m in enumerate(mondays):
                if first <= m < first + timedelta(weeks=BUILD_WEEKS):
                    demand[t][k] += hours * signed[t] / sum(signed.values()) / BUILD_WEEKS
    key = {"short": {}, "spare": {}}
    for t in teams:
        usable = heads[t] * PERSON_HOURS
        gaps = [d - usable for d in demand[t]]
        if max(gaps) > 0.05:
            k = next(i for i, g in enumerate(gaps) if g > 0)
            key["short"][t] = {"shortfall_hours_per_week": max(gaps), "starts_week": mondays[k].isoformat(),
                               "hire_by": (mondays[k] - timedelta(weeks=HIRING_LEAD_WEEKS)).isoformat()}
        else:
            spare = sum(usable - d for d in demand[t]) / HORIZON
            if spare >= usable * SPARE_PCT / 100:
                key["spare"][t] = {"spare_hours_per_week": spare}
    return key


def run_exam(cos=None) -> dict:
    if cos is None:
        from wiring.build_company_os import build_company_os
        cos = build_company_os(agents=("hiring_forecast",))
    key = derive_key(cos.data_conn)
    res = cos.run("hiring_forecast", "P90", "devx-internal", inputs={"as_of": TODAY})
    cases = cos.memory.cases(area_id="devx-internal", agent="hiring_forecast")
    got = {"short": {}, "spare": {}}
    for c in cases:
        if c["run_id"] == res.run_id:
            kind, team = c["subject"].split(":", 1)
            got[kind][team] = json.loads(c["evidence"]) if isinstance(c["evidence"], str) else c["evidence"]
    checks = []
    for kind in ("short", "spare"):
        for team in sorted(set(key[kind]) | set(got[kind])):
            want, have = key[kind].get(team), got[kind].get(team)
            ok = want is not None and have is not None and _agree(kind, want, have)
            checks.append({"team": team, "kind": kind, "ok": ok, "in_key": want is not None, "in_pack": have is not None})
    wrong = [c for c in checks if not c["ok"]]
    summary = {"run_status": res.status, "run_reason": res.reason, "key_short": sorted(key["short"]),
               "key_spare": sorted(key["spare"]), "pack_short": sorted(got["short"]), "pack_spare": sorted(got["spare"]),
               "checked": len(checks), "agree": len(checks) - len(wrong), "disagree": len(wrong), "disagreements": wrong,
               "agreed": res.status in ("done", "held") and not wrong, "key_is": "derived from the raw tables, not planted"}
    for metric in ("checked", "agree", "disagree"):
        cos.memory.add_score("hiring_forecast_exam", "hiring_forecast", metric, summary[metric], detail=None)
    return summary


def _agree(kind, want, have):
    if kind == "spare":
        return abs(want["spare_hours_per_week"] - have["spare_hours_per_week"]) <= TOLERANCE_HOURS
    return (abs(want["shortfall_hours_per_week"] - have["shortfall_hours_per_week"]) <= TOLERANCE_HOURS
            and want["starts_week"] == have["starts_week"] and want["hire_by"] == have["hire_by"])
