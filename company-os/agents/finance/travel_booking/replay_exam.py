"""Replay exam: run each request in exam_requests.json and check the policy, the totals and the approval gate.

The checks recompute the rules from travel_policy.json, not from the ranking code.
"""
import json
from pathlib import Path

from company_data.generate_trips import FLIGHT_HOURS, POLICY_RATE
from wiring.build_company_os import build_company_os

from . import service
from .request_parser import nights_of
from .policy_ranking import rooms_for

AGENT, APPROVER = "travel_booking", "P01"
HERE = Path(__file__).parent


def _flight_violations(flights, request, policy):
    hours = FLIGHT_HOURS.get((request["from_city"], request["to_city"])) or FLIGHT_HOURS[(request["to_city"], request["from_city"])]
    bad = 0
    for f in flights:
        bad += f["cabin"] != "economy" and hours < policy["economy_only_under_hours"]
        bad += not policy["depart_window"]["from"] <= f["depart_time"] <= policy["depart_window"]["to"]
        bad += f["total_inr"] != f["fare_inr"] * request["pax"]
    bad += [f["fare_inr"] for f in flights] != sorted(f["fare_inr"] for f in flights)
    return bad


def _hotel_violations(hotels, request):
    rooms, nights = rooms_for(request["pax"]), nights_of(request)
    bad = sum(h["rate_inr"] > POLICY_RATE[request["to_city"]] or h["total_inr"] != h["rate_inr"] * nights * rooms for h in hotels)
    return bad + ([h["rate_inr"] for h in hotels] != sorted(h["rate_inr"] for h in hotels))


def _bookings(cos):
    return cos.memory.conn.execute("SELECT COUNT(*) FROM travel_bookings").fetchone()[0]


def run_exam(cos=None) -> dict:
    cos = cos or build_company_os(agents=(AGENT,))
    policy = json.loads((HERE / "travel_policy.json").read_text())
    cases = json.loads((HERE / "exam_requests.json").read_text())["cases"]
    failed, violations, booked_early, double, wrong_book = [], 0, 0, 0, 0
    for case in cases:
        count = _bookings(cos)
        r = service.request_trip(cos, case["caller"], case["request"])
        ok = r["status"] == case["expect"]
        if r["status"] == "held":
            row = service.requests_for(cos, case["caller"])[0]
            v = _flight_violations(r["flights"], row["request"], policy) + _hotel_violations(r["hotels"], row["request"])
            violations += v
            ok = ok and v == 0 and len(r["flights"]) == 3 and len(r["hotels"]) == (3 if row["request"].get("return_on") else 0)
            before = _bookings(cos)
            booked_early += before - count
            if case["then"]:
                cos.approvals.decide(r["approval_id"], case["then"] == "approve", APPROVER)
                first = service.booking_after_approval(cos, r["approval_id"])
                second = service.booking_after_approval(cos, r["approval_id"])
                gain = _bookings(cos) - before
                if case["then"] == "approve":
                    ok = ok and first["status"] == "booked" and gain == 1
                    double += second["status"] == "booked"
                else:
                    wrong_book += gain
                    ok = ok and gain == 0 and first["status"] == "skipped"
        if not ok:
            failed.append(case["id"])
    metrics = {"cases": len(cases), "passed": len(cases) - len(failed), "failed": len(failed),
               "policy_violations": violations, "booked_before_approval": booked_early, "double_bookings": double,
               "booked_after_deny": wrong_book}
    for name, value in metrics.items():
        cos.memory.add_score("replay", AGENT, name, value, detail={"failed": failed})
    return {**metrics, "failed_ids": failed}


def judge(raw):
    ok = raw["failed"] == 0 and not any(raw[k] for k in ("policy_violations", "booked_before_approval", "double_bookings", "booked_after_deny"))
    text = (f"{raw['passed']}/{raw['cases']} requests right; policy violations {raw['policy_violations']}; "
            f"booked before approval {raw['booked_before_approval']}; booked twice {raw['double_bookings']}; "
            f"booked after deny {raw['booked_after_deny']}")
    return "top 3 follow the policy; nothing books without approval", text, ok


if __name__ == "__main__":
    print(json.dumps(run_exam(), indent=1))
