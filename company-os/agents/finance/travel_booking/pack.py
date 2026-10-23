"""Travel booking agent pack: searches fares, ranks by the travel policy, shows the best 3, and holds the booking for an Admin."""
import json
import re

from company_data.generate_trips import POLICY_RATE
from control_plane.connectors.fare_search import fare_tools
from contract.types import ToolCall, ToolSpec
from lifecycle_kit.action_tools import make_send_private_message
from lifecycle_kit.agent_pack import AgentPack

from . import booking_store
from .policy_ranking import load_policy, rank_flights, rank_hotels, rank_round_trips, rooms_for
from .request_parser import RequestError, nights_of, normalize_request

AREA = "devx-internal"
MARKER = "FACTS_JSON:"
FLIGHT_NO_RE = re.compile(r"\b(?:KSA|SRG|NMB|TRG) \d{3}\b")
OTHER_TRIP_RE = re.compile(r"\b(?:TR\d{3}|TRQ\d{4})\b")


def make_book_travel(conn, clock) -> ToolSpec:
    """The risky tool. It runs only after an Admin approves; it re-checks the options against the stored request."""
    def fn(args, ctx):
        req = booking_store.get_request(conn, args["request_id"])
        if req is None:
            raise ValueError("unknown travel request")
        if req["booking"]:
            raise ValueError("this request is already booked")
        flight = next((f for f in (req["round_trips"] or req["flights"]) if f["option_id"] == args["flight_option_id"]), None)
        hotel_id = args.get("hotel_option_id") or None
        hotel = next((h for h in req["hotels"] if h["option_id"] == hotel_id), None) if hotel_id else None
        if flight is None or (hotel_id and hotel is None) or (req["hotels"] and hotel is None):
            raise ValueError("that option is not one of the options shown")
        total = flight["total_inr"] + (hotel["total_inr"] if hotel else 0)
        if total != args["total_inr"]:
            raise ValueError("the total does not match the options")
        ref = booking_store.add_booking(conn, req["request_id"], flight["option_id"], hotel_id, req["request"]["pax"],
                                        total, clock.now)
        return f"booked {ref}"
    return ToolSpec(
        name="book_travel", description="Book the chosen flight and hotel (simulated). Waits for an Admin's approval.",
        params={"type": "object", "required": ["request_id", "flight_option_id", "total_inr"], "properties": {
            "request_id": {"type": "string"}, "flight_option_id": {"type": "string"},
            "hotel_option_id": {"type": "string"}, "total_inr": {"type": "integer"}}},
        fn=fn, risky=True)


def _read(ctx, name, args):
    """Run one search tool through the guard. Returns the parsed JSON, or {} when the tool was refused."""
    try:
        data = json.loads(ctx.notes["invoke_tool"](name, args)["result"])
    except ValueError:
        return {}
    return data if isinstance(data, dict) and "error" not in data else {}


class TravelBookingPack(AgentPack):
    name = "travel_booking"
    starter_roles = frozenset({"ceo", "rnd_lead", "finance_lead", "csm", "growth"})
    approver_roles = frozenset({"ceo", "finance_lead"})

    def __init__(self, parts):
        self.parts = parts
        self.conn = parts.memory.conn
        booking_store.ensure_schema(self.conn)

    def tools(self):
        return [*fare_tools(), make_book_travel(self.conn, self.parts.clock), make_send_private_message(self.parts.outbox)]

    def system_prompt(self):
        return ("You are the travel booking agent for DevX. Write a short, plain letter that shows the best flights and "
                "hotels you are given. Use only the numbers, times and flight numbers you are given. Say why each option "
                "ranks where it does. Say that nothing is booked until an Admin approves. Name no person. "
                'Answer with JSON only: {"letter": "<the letter>"}.')

    def record(self, ctx):
        try:
            request = normalize_request(ctx.task.inputs.get("request"))
        except RequestError:
            return {"request": None}
        request["nights"] = nights_of(request)
        request["rooms"] = rooms_for(request["pax"])
        flights = _read(ctx, "search_flights", {"from_city": request["from_city"], "to_city": request["to_city"],
                                                "date": request["depart_on"], "pax": request["pax"]})
        hotels = _read(ctx, "search_hotels", {"city": request["to_city"], "check_in": request["depart_on"],
                                              "nights": request["nights"], "rooms": request["rooms"]}) if request["nights"] else {}
        back = _read(ctx, "search_flights", {"from_city": request["to_city"], "to_city": request["from_city"],
                                             "date": request["return_on"], "pax": request["pax"]}) if request.get("return_on") else {}
        return {"request": request, "flights": flights.get("flights", []), "hotels": hotels.get("hotels", []),
                "return_flights": back.get("flights", [])}

    def understand(self, ctx, recorded):
        request = recorded["request"]
        if not request or not recorded["flights"]:
            return {"quiet": True}
        policy = load_policy()
        top_f, bad_f = rank_flights(recorded["flights"], request, policy)
        top_h, bad_h = rank_hotels(recorded["hotels"], request, policy)
        if not top_f or (request["nights"] and not top_h):
            return {"quiet": True}
        trips = []
        if recorded["return_flights"]:
            back = {**request, "from_city": request["to_city"], "to_city": request["from_city"]}
            top_r, bad_r = rank_flights(recorded["return_flights"], back, policy)
            bad_f += [{**b, "label": "Return " + b["label"]} for b in bad_r]
            trips = rank_round_trips(top_f, top_r, request, policy) if top_r else []
        understood = {"request": {k: v for k, v in request.items() if k not in ("purpose", "client_id")},
                      "flights": top_f, "hotels": top_h, "round_trips": trips, "out_of_policy": bad_f + bad_h,
                      "city_rate_inr": POLICY_RATE[request["to_city"]]}
        ctx.notes["travel"] = understood
        return understood

    def decision_prompt(self, understood):
        return (f"A DevX person asked for travel. These options were found and ranked by the travel policy.\n{MARKER}\n"
                f"{json.dumps(understood, sort_keys=True, separators=(',', ':'))}\n"
                'Reply with final JSON only: {"letter": "<the letter>"}. List each flight and hotel with its price per '
                "person or night and its total, and say why it ranks where it does.")

    def parse_decision(self, final_text):
        text = final_text.strip()
        data = json.loads(text[text.find("{"):text.rfind("}") + 1])
        return {"letter": str(data["letter"])}

    def check(self, ctx, decision, understood):
        text, req, problems = decision["letter"], understood["request"], []
        trips = understood.get("round_trips") or []
        for rt in trips:
            if rt["total_inr"] != rt["fare_inr"] * req["pax"] or rt["fare_inr"] != rt["outbound"]["fare_inr"] + rt["return"]["fare_inr"]:
                problems.append(f"the total for round trip {rt['outbound']['flight_no']} and {rt['return']['flight_no']} is wrong")
        for f in understood["flights"]:
            if not f["policy_ok"]:
                problems.append(f"flight {f['flight_no']} is out of policy")
            if f["total_inr"] != f["fare_inr"] * req["pax"]:
                problems.append(f"the total for {f['flight_no']} does not match {req['pax']} people")
        for h in understood["hotels"]:
            if not h["policy_ok"]:
                problems.append(f"hotel {h['hotel']} is out of policy")
            if h["total_inr"] != h["rate_inr"] * req["nights"] * req["rooms"]:
                problems.append(f"the total for {h['hotel']} does not match the stay")
        shown = _amounts(understood)
        for raw in re.findall(r"INR\s*(\d[\d,]*)", text):
            if int(raw.replace(",", "")) not in shown:
                problems.append(f"amount INR {raw} does not match the computed data")
        numbers = ({n for rt in trips for n in (rt["outbound"]["flight_no"], rt["return"]["flight_no"])} if trips
                   else {f["flight_no"] for f in understood["flights"]})
        for no in set(FLIGHT_NO_RE.findall(text)) - numbers:
            problems.append(f"flight {no} is not one of the options")
        for no in sorted(numbers - set(FLIGHT_NO_RE.findall(text))):
            problems.append(f"flight {no} is missing from the letter")
        if "nothing is booked" not in text.lower():
            problems.append("the letter must say that nothing is booked until an Admin approves")
        problems += self._other_trip_problems(text, ctx)
        return problems

    def _other_trip_problems(self, text, ctx):
        """The letter goes to one person. It must name no person and no other trip or request."""
        problems = [f"the letter names {x}; it may show only this trip" for x in sorted(set(OTHER_TRIP_RE.findall(text)))]
        for (name,) in self.parts.data_conn.execute("SELECT name FROM people"):
            for word in {name, name.split()[0]}:
                if re.search(rf"\b{re.escape(word)}\b", text, re.I):
                    problems.append(f"the letter names a person ({word}); it may show only this trip")
        return problems

    def act(self, ctx, decision):
        t = ctx.notes["travel"]
        hotel = t["hotels"][0] if t["hotels"] else None
        first = (t["round_trips"] or t["flights"])[0]
        total = first["total_inr"] + (hotel["total_inr"] if hotel else 0)
        book = {"request_id": ctx.task.inputs["request_id"], "flight_option_id": first["option_id"],
                "hotel_option_id": hotel["option_id"] if hotel else "", "total_inr": total}
        return [ToolCall("act-letter", "send_private_message",
                         {"to_person_id": ctx.task.caller_id, "text": decision["letter"], "kind": "travel_options"}),
                ToolCall("act-book", "book_travel", book)]

    def remember(self, ctx, decision, acted):
        t = ctx.notes["travel"]
        held = bool(ctx.held)
        booking_store.update_request(
            self.conn, ctx.task.inputs["request_id"], run_id=ctx.run_id, status="held" if held else "failed",
            approval_id=ctx.held[0] if held else None, flights_json=t["flights"], hotels_json=t["hotels"], round_trips_json=t["round_trips"],
            out_of_policy_json=t["out_of_policy"], letter=decision["letter"])
        return {"request_id": ctx.task.inputs["request_id"], "held": held}


def _amounts(facts):
    """Every amount in the facts: the *_inr numbers and any INR amount inside the 'why' sentences."""
    found = set()

    def walk(key, value):
        if isinstance(value, dict):
            for k, v in value.items():
                walk(k, v)
        elif isinstance(value, list):
            for v in value:
                walk(key, v)
        elif isinstance(value, bool):
            return
        elif isinstance(value, (int, float)) and key.endswith("_inr"):
            found.add(int(value))
        elif isinstance(value, str):
            found.update(int(x.replace(",", "")) for x in re.findall(r"INR\s*(\d[\d,]*)", value))
    walk("facts", facts)
    return found


def make_pack(parts):
    return TravelBookingPack(parts)
