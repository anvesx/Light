"""Replay exam: run finance_watch as of each planted case's date; score found, missed and false alarms.

Only this file and the tests read the answer key.
"""
import json
import os

from company_data import DB_PATH
from wiring.build_company_os import build_company_os

KEY_PATH = os.path.join(os.path.dirname(DB_PATH), "answer_keys.json")
AGENT, AREA, CALLER = "finance_watch", "devx-internal", "P07"


def _flagged(cos, as_of):
    """Findings the agent produced as of one date. A run that failed or stayed quiet gives none."""
    result = cos.run(AGENT, CALLER, AREA, inputs={"as_of": as_of})
    if result.status not in ("done", "held") or result.final_text == "quiet":
        return []
    return json.loads(result.final_text).get("findings", [])


def _case_match(case, finding):
    ids, kind = set(finding["ids"]), finding["kind"]
    if case["signal"] == "duplicate_invoice":
        return kind == "duplicate_invoice" and set(case["invoice_ids"]) <= ids
    if case["signal"] == "large_payment_to_new_vendor":
        return kind == "large_payment_new_vendor" and case["payment_id"] in ids
    if case["signal"] == "budget_overrun":
        return kind == "budget_overrun" and f"{case['team']}:{case['month']}:{case['category']}" in ids
    return kind == "travel_share_of_salary" and f"{case['team']}:{case['month']}" in ids


def _look_alike_dates(cos, key):
    """Dates when a look-alike could be wrongly flagged: each monthly bill, and the day of the big old-vendor payment."""
    dates = {}
    for la in key["look_alikes"]:
        if la.get("vendor_ids"):
            marks = ",".join("?" * len(la["vendor_ids"]))
            rows = cos.data_conn.execute(f"SELECT invoice_id, date FROM invoices WHERE vendor_id IN ({marks})",
                                         la["vendor_ids"]).fetchall()
            dates[la["case_id"]] = sorted({r["date"] for r in rows}), {r["invoice_id"] for r in rows}
        else:
            row = cos.data_conn.execute("SELECT date FROM payments WHERE payment_id = ?", (la["payment_id"],)).fetchone()
            dates[la["case_id"]] = [row["date"], row["date"][:8] + "28"], {la["payment_id"]}
    return dates


def run_exam(cos=None) -> dict:
    cos = cos or build_company_os(agents=(AGENT,))
    with open(KEY_PATH) as fh:
        key = json.load(fh)["finance_watch"]
    cases, found, missed = [], [], []
    for case in key["cases"]:
        flagged = _flagged(cos, case["first_detectable_on"])
        hit = any(_case_match(case, f) for f in flagged)
        (found if hit else missed).append(case["case_id"])
        cases.append({"case_id": case["case_id"], "as_of": case["first_detectable_on"], "found": hit,
                      "findings": len(flagged)})
    false_alarms = []
    for la in key["look_alikes"]:
        dates, ids = _look_alike_dates(cos, key)[la["case_id"]]
        for as_of in dates:
            if any(ids & set(f["ids"]) for f in _flagged(cos, as_of)):
                false_alarms.append({"case_id": la["case_id"], "as_of": as_of})
    metrics = {"cases": len(key["cases"]), "found": len(found), "missed": len(missed),
               "look_alikes": len(key["look_alikes"]), "false_alarms": len(false_alarms),
               "recall": round(len(found) / len(key["cases"]), 3)}
    for name, value in metrics.items():
        cos.memory.add_score("replay", AGENT, name, value, detail={"missed": missed, "false_alarms": false_alarms})
    return {**metrics, "found_ids": found, "missed_ids": missed, "false_alarm_list": false_alarms, "cases_detail": cases}


if __name__ == "__main__":
    print(json.dumps(run_exam(), indent=1))


def judge(r):
    """Return (what is measured, result text, passed) for this exam's raw result."""
    ok = r["found"] == r["cases"] and r["false_alarms"] == 0
    return "planted money cases found, no false alarms", \
        f"{r['found']} of {r['cases']} found, {r['false_alarms']} false alarms", ok
