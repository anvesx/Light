"""Replay exam for the delivery progress agent: run it daily on every client and score it against the planted cases."""
import json
import os
from datetime import date, timedelta

from company_data.simulated_today import TODAY

KEY_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "company_data", "answer_keys.json")
START = "2026-08-10"
CASE_SIGNALS = {"merged_work_outside_scope": "unbilled_work", "scope_item_reworked_after_client_meetings": "scope_rework",
                "merge_pace_too_slow_for_planned_end": "behind_deadline"}
LOOK_SIGNALS = {"unlinked_small_chore_prs": "unbilled_work", "scope_item_two_revisions": "scope_rework",
                "on_track": "behind_deadline"}


def run_exam(cos=None) -> dict:
    if cos is None:
        from wiring.build_company_os import build_company_os
        cos = build_company_os(agents=("delivery_progress",))
    with open(KEY_PATH) as fh:
        key = json.load(fh)["delivery_progress"]
    first_flag = _replay(cos)

    results = []
    for case in key["cases"]:
        prefix = f"{CASE_SIGNALS[case['signal']]}:{case['project_id']}"
        found_on = next((d for s, d in sorted(first_flag.items()) if s.startswith(prefix)), None)
        lag = _days(found_on, case["first_detectable_on"]) if found_on else None
        results.append({"case_id": case["case_id"], "subject": prefix, "status": "found" if found_on else "missed",
                        "first_flagged_on": found_on, "first_detectable_on": case["first_detectable_on"],
                        "lag_days": lag})
    false_alarms = []
    for look in key["look_alikes"]:
        prefix = f"{LOOK_SIGNALS[look['signal']]}:{look['project_id']}"
        hit = [s for s in first_flag if s.startswith(prefix)]
        if hit:
            false_alarms.append({"case_id": look["case_id"], "subject": hit[0], "first_flagged_on": first_flag[hit[0]]})
    planted = {r["subject"] for r in results} | {f["subject"] for f in false_alarms}
    lags = [r["lag_days"] for r in results if r["lag_days"] is not None]
    summary = {"planted": len(results), "found": len(lags), "missed": len(results) - len(lags),
               "false_alarms": len(false_alarms), "mean_lag_days": round(sum(lags) / len(lags), 2) if lags else None,
               "max_lag_days": max(lags) if lags else None, "min_lag_days": min(lags) if lags else None,
               "other_flags": sorted(s for s in first_flag if not any(s.startswith(p) for p in planted)),
               "cases": results, "false_alarm_cases": false_alarms}
    for metric in ("planted", "found", "missed", "false_alarms", "mean_lag_days", "max_lag_days"):
        if summary[metric] is not None:
            cos.memory.add_score("delivery_progress_replay", "delivery_progress", metric, summary[metric], detail=None)
    return summary


def _replay(cos):
    """Run every client area once per day. Returns {subject: first day flagged}."""
    clients = [r["client_id"] for r in cos.data_conn.execute("SELECT client_id FROM clients ORDER BY client_id")]
    first = {}
    day = date.fromisoformat(START)
    while day.isoformat() <= TODAY:
        for client in clients:
            res = cos.run("delivery_progress", "system", client, trigger_kind="timer", inputs={"as_of": day.isoformat()})
            for case in cos.memory.cases(area_id=client, agent="delivery_progress"):
                if case["run_id"] == res.run_id:
                    first.setdefault(case["subject"], day.isoformat())
        day += timedelta(days=1)
    return first


def _days(later, earlier):
    return (date.fromisoformat(later) - date.fromisoformat(earlier)).days
