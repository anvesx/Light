"""Replay exam: scan each day with the pack's reading tools and score the answer key. Only this file reads it."""
import json
import os
from datetime import date
from types import SimpleNamespace

from company_data.simulated_today import TODAY
from connectors.tool_reply import next_day
from contract.types import Task

from .pattern_rules import KIND_CASH, KIND_REMAKE, KIND_SELF, find_patterns

KEY_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "company_data", "answer_keys.json")
SIGNAL_KIND = {"many_cash_refunds": KIND_CASH, "self_approved_discounts": KIND_SELF, "repeated_free_remakes": KIND_REMAKE}
LOOKALIKE_KIND = {"many_card_refunds_reason_recall": KIND_CASH, "many_discounts_approved_by_manager_in_sale_week": KIND_SELF}
SCAN_FROM = "2026-05-01"


def _day_patterns(pack, area_id, day):
    ctx = SimpleNamespace(task=Task(agent="fraud_watch", caller_id="system", area_id=area_id, trigger_kind="test",
                                    inputs={"as_of": day}))
    tools = {t.name: t.fn for t in pack.tools()}
    args = pack.read_args()
    args.pop("as_of", None)
    read = [json.loads(tools[n](args, ctx)) for n in ("refunds_by_staff", "discounts_by_staff", "remakes_by_staff")]
    return find_patterns(*read)


def run_exam(cos=None) -> dict:
    if cos is None:
        from wiring.build_company_os import build_company_os
        cos = build_company_os(agents=("fraud_watch",))
    with open(KEY_PATH) as f:
        key = json.load(f)["fraud_watch"]
    pack = cos.packs["fraud_watch"]
    area_id = cos.data_conn.execute("SELECT DISTINCT client_id FROM stores").fetchone()[0]
    by_day, day = {}, SCAN_FROM
    while day <= TODAY:
        by_day[day] = _day_patterns(pack, area_id, day)
        day = next_day(day)

    cases, matched = [], set()
    for c in key["cases"]:
        kind = SIGNAL_KIND[c["signal"]]
        first = next((d for d in sorted(by_day) if d >= c["first_detectable_on"]
                      and any(p["kind"] == kind and p["staff_id"] == c["person_id"] for p in by_day[d])), None)
        matched.add((kind, c["person_id"]))
        late = None if first is None else (_days(first) - _days(c["first_detectable_on"]))
        cases.append({"case_id": c["case_id"], "found": first is not None, "found_on": first, "days_late": late})

    look_alikes = []
    for la in key["look_alikes"]:
        kind = LOOKALIKE_KIND[la["signal"]]
        hits = sorted({d for d, ps in by_day.items() for p in ps if p["kind"] == kind and p["store_id"] == la["store_id"]})
        look_alikes.append({"case_id": la["case_id"], "flagged": bool(hits), "first_flagged_on": hits[0] if hits else None})

    other = sorted({(p["kind"], p["staff_id"]) for ps in by_day.values() for p in ps} - matched)
    found = sum(c["found"] for c in cases)
    result = {"cases": cases, "look_alikes": look_alikes, "found": found, "missed": len(cases) - found,
              "false_alarms": sum(la["flagged"] for la in look_alikes),
              "other_flags": [list(o) for o in other]}
    for metric in ("found", "missed", "false_alarms"):
        cos.memory.add_score("replay", "fraud_watch", metric, result[metric], detail=result)
    return result


def _days(day):
    return date.fromisoformat(day).toordinal()
