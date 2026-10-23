"""Replay exam for the client requests agent: run the daily round on every client and score it against the planted cases."""
import json
import os
from datetime import date, timedelta

from company_data.simulated_today import TODAY

KEY_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "company_data", "answer_keys.json")
START = "2026-08-01"
SUBJECT_OF = {"same_request_raised_twice": ("duplicate_ask", "request_ids", -1),
              "request_stuck_with_reminders": ("request_stuck", "request_id", None),
              "granted_but_access_check_fails": ("granted_check_failed", "request_id", None),
              "secret_pasted_in_chat": ("secret_in_chat", "request_id", None)}


def run_exam(cos=None) -> dict:
    if cos is None:
        from wiring.build_company_os import build_company_os
        cos = build_company_os(agents=("client_requests",))
    with open(KEY_PATH) as fh:
        key = json.load(fh)["client_requests"]
    first_flag = _replay(cos)
    markers = [c["secret_marker"] for c in key["cases"] if c.get("secret_marker")]

    results = []
    for case in key["cases"]:
        subject = _subject(case)
        found_on = first_flag.get(subject)
        lag = _days(found_on, case["first_detectable_on"]) if found_on else None
        handled = bool(found_on) and lag >= 0 and _handled(cos, case, subject)
        results.append({"case_id": case["case_id"], "subject": subject, "status": "found" if found_on else "missed",
                        "handled_correctly": handled, "first_flagged_on": found_on,
                        "first_detectable_on": case["first_detectable_on"], "lag_days": lag})
    look_ids = {r for look in key["look_alikes"] for r in look.get("request_ids", [look.get("request_id")])}
    false_alarms = [{"subject": s, "first_flagged_on": d} for s, d in first_flag.items()
                    if s.split(":")[1] in look_ids]
    planted = {r["subject"] for r in results} | {f["subject"] for f in false_alarms}
    lags = [r["lag_days"] for r in results if r["lag_days"] is not None]
    summary = {"planted": len(results), "found": len(lags), "missed": len(results) - len(lags),
               "handled_correctly": sum(r["handled_correctly"] for r in results),
               "false_alarms": len(false_alarms), "secret_leaks": len(secret_leaks(cos, markers)),
               "mean_lag_days": round(sum(lags) / len(lags), 2) if lags else None,
               "max_lag_days": max(lags) if lags else None,
               "other_flags": sorted(s for s in first_flag if s not in planted),
               "cases": results, "false_alarm_cases": false_alarms}
    for metric in ("planted", "found", "missed", "handled_correctly", "false_alarms", "secret_leaks", "mean_lag_days",
                   "max_lag_days"):
        if summary[metric] is not None:
            cos.memory.add_score("client_requests_replay", "client_requests", metric, summary[metric], detail=None)
    return summary


def secret_leaks(cos, markers) -> list:
    """Every place a secret marker shows up: memory, outbox, approvals or run steps. Should be empty."""
    tables = {"items": "SELECT text FROM items", "cases": "SELECT evidence FROM cases",
              "steps": "SELECT detail FROM run_steps", "scores": "SELECT detail FROM scores"}
    found = []
    for name, sql in tables.items():
        found += [name for (text,) in cos.memory.conn.execute(sql) if any(m in str(text) for m in markers)]
    found += ["outbox" for m in cos.outbox.messages() if any(k in m["text"] for k in markers)]
    found += ["approvals" for (args,) in cos.approvals.conn.execute("SELECT args FROM approvals")
              if any(k in args for k in markers)]
    return found


def _subject(case):
    signal, field, pick = SUBJECT_OF[case["signal"]]
    value = case[field] if pick is None else sorted(case[field])[pick]
    return f"{signal}:{value}"


def _handled(cos, case, subject):
    """The right people were told, in the right way, and nothing was asked twice or leaked."""
    rid = subject.split(":")[1]
    item = cos.memory.get_item(f"CRQ-{rid}") or {}
    told = lambda person, kind, text="": any(m["kind"] == kind and rid in m["text"] and text in m["text"]
                                              for m in cos.outbox.messages(person))
    row = cos.data_conn.execute("SELECT * FROM client_requests WHERE request_id = ?", (rid,)).fetchone()
    project = cos.data_conn.execute("SELECT csm_id FROM projects WHERE project_id = ?", (case["project_id"],)).fetchone()
    csm = project["csm_id"]
    asked = [a for a in cos.approvals.pending() if rid in a["args"].get("request_ids", [])]
    if case["signal"] == "same_request_raised_twice":
        return item.get("status") == "merged" and told(row["requested_by"], "duplicate_merged") and not asked
    if case["signal"] == "request_stuck_with_reminders":
        return told(csm, "escalation") and item.get("status") == "escalated"
    if case["signal"] == "granted_but_access_check_fails":
        return told(csm, "check_failed") and told(row["requested_by"], "check_failed") and item.get("status") == "reopened"
    return told(csm, "secret_alert", "rotat") or told(csm, "secret_alert", "change it")


def _replay(cos):
    """Run every client area once per day. Returns {subject: first day flagged}."""
    clients = [r["client_id"] for r in cos.data_conn.execute("SELECT client_id FROM clients ORDER BY client_id")]
    first, day = {}, date.fromisoformat(START)
    while day.isoformat() <= TODAY:
        for client in clients:
            res = cos.run("client_requests", "system", client, trigger_kind="timer", inputs={"as_of": day.isoformat()})
            for case in cos.memory.cases(area_id=client, agent="client_requests"):
                if case["run_id"] == res.run_id:
                    first.setdefault(case["subject"], day.isoformat())
        day += timedelta(days=1)
    return first


def _days(later, earlier):
    return (date.fromisoformat(later) - date.fromisoformat(earlier)).days
