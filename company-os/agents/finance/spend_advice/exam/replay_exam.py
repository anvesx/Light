"""Replay exam: ask the spend advisor about each planted saving's day; score found, missed and false alarms.

Only this file and the tests read the answer key.
"""
import json
import os

from company_data import DB_PATH
from wiring.build_company_os import build_company_os

KEY_PATH = os.path.join(os.path.dirname(DB_PATH), "answer_keys.json")
AGENT, AREA, CALLER = "spend_advisor", "devx-internal", "P01"
QUESTION = "Where can we save on travel?"


def _answer(cos, day):
    """The letter and the saving lines the agent gave for one day. A failed run gives nothing."""
    result = cos.run(AGENT, CALLER, AREA, inputs={"question": QUESTION, "from": day, "to": day, "as_of": day})
    if result.status != "done":
        return ""
    return json.loads(result.final_text)["answer"]


def _alternatives_check(cos) -> dict:
    """Every cheaper_option_existed trip has a concrete option, and each option is a real row in the raw tables."""
    from control_plane.connectors.spend_tools import make_trip_alternatives
    from contract.types import RunContext, Task
    ctx = RunContext("EXAM", Task(AGENT, CALLER, AREA, "request", inputs={}), None)
    cards = json.loads(make_trip_alternatives(cos.data_conn).fn({"from": "2000-01-01"}, ctx))["trips"]
    conn, bare, wrong = cos.data_conn, [], []
    for c in cards:
        flights, hotels = c["cheaper_flights"], c["cheaper_hotels"]
        if c["verdict"] == "cheaper_option_existed" and not (flights or hotels):
            bare.append(c["trip_id"])
        booked = conn.execute("SELECT booked_on FROM trips WHERE trip_id = ?", (c["trip_id"],)).fetchone()[0]
        for f in flights:
            if f["rule"] == "same_city_trips":
                row = conn.execute("SELECT 1 FROM trips WHERE flight_no = ? AND fare_inr = ? AND depart_time = ?",
                                   (f["flight_no"], f["fare_inr"], f["depart_time"])).fetchone()
            else:
                row = conn.execute("SELECT 1 FROM fare_options WHERE trip_id = ? AND flight_no = ? AND fare_inr = ? "
                                   "AND depart_time = ? AND seen_on = ? AND seen_on <= ? AND fare_inr < ?",
                                   (c["trip_id"], f["flight_no"], f["fare_inr"], f["depart_time"], f["seen_on"], booked,
                                    c["paid"]["fare_inr"])).fetchone()
            if not row or not f["carrier"] or not f["depart_time"]:
                wrong.append(c["trip_id"])
        for h in hotels:
            row = conn.execute("SELECT 1 FROM hotel_options o JOIN hotel_stays s USING(stay_id) WHERE s.trip_id = ? AND o.hotel = ? "
                               "AND o.rate_inr = ? AND o.rate_inr < s.rate_inr", (c["trip_id"], h["hotel"], h["rate_inr"])).fetchone()
            if not row:
                wrong.append(c["trip_id"])
    return {"alt_trips": len(cards), "alt_without_option": len(bare), "alt_wrong": len(wrong)}


def run_exam(cos=None) -> dict:
    cos = cos or build_company_os(agents=(AGENT,))
    with open(KEY_PATH) as fh:
        key = json.load(fh)["spend_advisor"]
    amounts = {"late_booking": "Booking a week earlier", "business_short_flight": "Economy would have saved",
               "same_city_trips": "One trip could have done both", "hotel_above_city_rate": "city rate is"}
    found, missed, false_alarms = [], [], []
    for case in key["cases"]:
        text = _answer(cos, case["first_detectable_on"])
        lines = [ln for ln in text.splitlines() if ln.startswith(case["trip_ids"][0] + " (") and amounts[case["signal"]] in ln]
        (found if lines else missed).append(case["case_id"])
    for la in key["look_alikes"]:
        text = _answer(cos, la["first_detectable_on"])
        tid = la["trip_ids"][0]
        flagged = [ln for ln in text.splitlines() if ln.startswith(tid + " (") and "No cheaper alternative" not in ln]
        if flagged:
            false_alarms.append(la["case_id"])
    metrics = {"cases": len(key["cases"]), "found": len(found), "missed": len(missed),
               "look_alikes": len(key["look_alikes"]), "false_alarms": len(false_alarms),
               "recall": round(len(found) / len(key["cases"]), 3), **_alternatives_check(cos)}
    for name, value in metrics.items():
        cos.memory.add_score("replay", AGENT, name, value, detail={"missed": missed, "false_alarms": false_alarms})
    return {**metrics, "found_ids": found, "missed_ids": missed, "false_alarm_list": false_alarms}




def judge(raw):
    ok = raw["missed"] == 0 and raw["false_alarms"] == 0 and raw["alt_without_option"] == 0 and raw["alt_wrong"] == 0
    text = (f"found {raw['found']}/{raw['cases']}, false alarms {raw['false_alarms']}; {raw['alt_trips']} trips checked, "
            f"{raw['alt_without_option']} without an option, {raw['alt_wrong']} options not in the raw tables")
    return "planted savings found; every cheaper trip names a real option", text, ok


if __name__ == "__main__":
    print(json.dumps(run_exam(), indent=1))
