"""Ranks flight and hotel options by the travel policy: policy first, then the lowest price. Pure code, no model."""
import json
from hashlib import sha1
from pathlib import Path

from company_data.generate_trips import POLICY_RATE
from control_plane.connectors.fare_search import route_hours

POLICY_PATH = Path(__file__).with_name("travel_policy.json")


def load_policy() -> dict:
    return json.loads(POLICY_PATH.read_text())


def inr(amount) -> str:
    """Indian digit grouping: INR 1,40,000."""
    s = str(int(amount))
    if len(s) > 3:
        head, tail, parts = s[:-3], s[-3:], []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        s = ",".join(([head] if head else []) + parts + [tail])
    return f"INR {s}"


def time12(hhmm: str) -> str:
    h, m = int(hhmm[:2]), int(hhmm[3:5])
    return f"{(h % 12) or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def rooms_for(pax: int, policy=None) -> int:
    per = (policy or load_policy())["people_per_room"]
    return -(-pax // per)


def _window_text(policy) -> str:
    w = policy["depart_window"]
    return f"{time12(w['from'])} to {time12(w['to'])}"


def flight_problem(option, hours, policy):
    """The policy rule a flight breaks, as a plain sentence, or None."""
    if option["cabin"] != "economy" and hours < policy["economy_only_under_hours"]:
        return f"Business class is not allowed on a flight under {policy['economy_only_under_hours']} hours."
    w = policy["depart_window"]
    if not w["from"] <= option["depart_time"] <= w["to"]:
        return f"It leaves at {time12(option['depart_time'])}, outside the {_window_text(policy)} window."
    return None


def rank_flights(options, request, policy=None):
    """Returns (top, out_of_policy). Flights without enough seats are dropped; out_of_policy lists the rule breakers."""
    policy = policy or load_policy()
    hours = route_hours(request["from_city"], request["to_city"])
    pax = request["pax"]
    good, bad = [], []
    for o in options:
        if o["seats_left"] < pax:
            continue
        problem = flight_problem(o, hours, policy)
        if problem:
            bad.append({"kind": "flight", "option_id": o["option_id"], "label": f"{o['flight_no']} at {time12(o['depart_time'])}",
                        "reason": problem})
        else:
            good.append(o)
    good.sort(key=lambda o: (o["fare_inr"], o["depart_time"], o["flight_no"]))
    top = []
    for n, o in enumerate(good[:policy["show_top"]], 1):
        why = (f"{o['cabin'].capitalize()}, a {hours} hour flight, {'non-stop' if not o['stops'] else '1 stop'}. "
               f"It leaves at {time12(o['depart_time'])}, inside the {_window_text(policy)} window. ")
        why += ("It is the cheapest option that fits the policy." if n == 1 else
                f"It costs {inr(o['fare_inr'] - good[0]['fare_inr'])} more a person than option 1.")
        top.append({**o, "policy_ok": True, "why": why, "total_inr": o["fare_inr"] * pax})
    return top, bad


def rank_hotels(options, request, policy=None):
    """Returns (top, out_of_policy). A hotel above the city rate is out of policy."""
    policy = policy or load_policy()
    rate = POLICY_RATE[request["to_city"]]
    good, bad = [], []
    for o in options:
        if o["rate_inr"] > rate:
            bad.append({"kind": "hotel", "option_id": o["option_id"], "label": o["hotel"],
                        "reason": f"{inr(o['rate_inr'])} a night is above the {o['city']} rate of {inr(rate)}."})
        else:
            good.append(o)
    good.sort(key=lambda o: (o["rate_inr"], -o["stars"], o["km_to_center"], o["hotel"]))
    top = []
    for n, o in enumerate(good[:policy["show_top"]], 1):
        why = f"{inr(o['rate_inr'])} a night is at or under the {o['city']} rate of {inr(rate)}. "
        why += ("It is the cheapest hotel that fits the policy." if n == 1 else
                f"It costs {inr(o['rate_inr'] - good[0]['rate_inr'])} more a night than option 1.")
        top.append({**o, "policy_ok": True, "why": why,
                    "total_inr": o["rate_inr"] * request["nights"] * request["rooms"]})
    return top, bad


def rank_round_trips(outbound, returns, request, policy=None):
    """The best round trips from the top outbound and top return flights: cheapest total first, with both flight numbers."""
    policy = policy or load_policy()
    pax, combos = request["pax"], []
    for o in outbound:
        for r in returns:
            combos.append((o["fare_inr"] + r["fare_inr"], o["depart_time"], r["depart_time"], o, r))
    combos.sort(key=lambda c: (c[0], c[1], c[2], c[3]["flight_no"], c[4]["flight_no"]))
    top = []
    for n, (fare, _, _, o, r) in enumerate(combos[:policy["show_top"]], 1):
        why = (f"Out {o['flight_no']} at {time12(o['depart_time'])}, back {r['flight_no']} at {time12(r['depart_time'])}. "
               "Both flights fit the policy. ")
        why += ("It is the cheapest round trip." if n == 1 else f"It costs {inr(fare - combos[0][0])} more a person than option 1.")
        key = f"{o['option_id']}|{r['option_id']}"
        top.append({"option_id": "RT-" + sha1(key.encode()).hexdigest()[:8], "outbound": o, "return": r, "fare_inr": fare,
                    "total_inr": fare * pax, "pax": pax, "policy_ok": True, "why": why})
    return top
