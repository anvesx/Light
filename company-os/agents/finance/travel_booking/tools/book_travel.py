"""The risky tool: books the chosen flight and hotel after an Admin approves."""
from contract.types import ToolSpec

from ..scripts import booking_store


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
