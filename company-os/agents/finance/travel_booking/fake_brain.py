"""Deterministic stand-in for the model: writes the travel options letter from the ranked facts, in plain words."""
import json

from contract.types import ModelReply

from .pack import MARKER
from .policy_ranking import inr, time12


def _flight_line(n, f, pax):
    stop = "non-stop" if not f["stops"] else "1 stop"
    arrive = time12(f["arrive_time"]) + (" the next day" if f.get("arrives_next_day") else "")
    return (f"{n}. {f['carrier']} {f['flight_no']}: leaves {time12(f['depart_time'])}, arrives {arrive}, {stop}. "
            f"{inr(f['fare_inr'])} a person, {inr(f['total_inr'])} for {pax}. Why: {f['why']}")


def _leg(f):
    return f"{f['carrier']} {f['flight_no']} leaves {time12(f['depart_time'])}, arrives {time12(f['arrive_time'])}"


def _trip_line(n, rt):
    return (f"{n}. Out: {_leg(rt['outbound'])}. Back: {_leg(rt['return'])}. {inr(rt['fare_inr'])} a person, "
            f"{inr(rt['total_inr'])} for {rt['pax']}. Why: {rt['why']}")


def _hotel_line(n, h):
    return (f"{n}. {h['hotel']}, {h['stars']} stars, {h['km_to_center']} km from the centre. "
            f"{inr(h['rate_inr'])} a night, {inr(h['total_inr'])} for the stay. Why: {h['why']}")


def _letter(facts):
    r = facts["request"]
    people = f"{r['pax']} {'person' if r['pax'] == 1 else 'people'}"
    trips = facts.get("round_trips") or []
    if trips:
        out = [f"Here are the best {len(trips)} round trips for {people}, {r['from_city']} to {r['to_city']}, out on "
               f"{r['depart_on']} and back on {r['return_on']}."]
        out += [_trip_line(n, rt) for n, rt in enumerate(trips, 1)]
    else:
        out = [f"Here are the best {len(facts['flights'])} flights for {people}, {r['from_city']} to {r['to_city']}, on {r['depart_on']}."]
        out += [_flight_line(n, f, r["pax"]) for n, f in enumerate(facts["flights"], 1)]
    if facts["hotels"]:
        night = "night" if r["nights"] == 1 else "nights"
        room = "room" if r["rooms"] == 1 else "rooms"
        out += ["", f"Best hotels in {r['to_city']} for {r['nights']} {night}, {r['rooms']} {room}:"]
        out += [_hotel_line(n, h) for n, h in enumerate(facts["hotels"], 1)]
    left = facts["out_of_policy"]
    if left:
        out += ["", f"{len(left)} other option{'s' if len(left) != 1 else ''} broke the travel policy and "
                    f"{'are' if len(left) != 1 else 'is'} not shown."]
    out += ["", "Nothing is booked yet. The booking waits for an Admin to approve it. Option 1 of each is held for approval."]
    return "\n".join(out)


def brain(request):
    prompt = request.messages[0]["content"]
    facts = json.loads(prompt.rsplit(MARKER, 1)[1].strip().split("\n", 1)[0])
    return ModelReply(text=json.dumps({"letter": _letter(facts)}))
