"""Simulated fare source: flights and hotels for a route and date. Same inputs always give the same options."""
from datetime import date, timedelta
from hashlib import sha1

from company_data.generate_trips import FLIGHT_CARRIERS, FLIGHT_HOURS, HOTELS, POLICY_RATE
from company_data.simulated_today import TODAY

from .tool_reply import DATE_RE, ToolInputError, build_tool, int_arg, str_arg

AREA = "devx-internal"
CARRIER_CODES = dict(zip(FLIGHT_CARRIERS, ("KSA", "SRG", "NMB", "TRG")))   # Kestrel, Sarang, Nimbus, Tarang
CARRIER_FACTOR = {"KSA": 1.10, "SRG": 1.00, "NMB": 0.93, "TRG": 1.04}
SLOTS = [h * 60 + m for h in range(5, 24) for m in (0, 30)]               # 5:00 AM to 11:30 PM, every 30 minutes
CABINS = ("economy", "business")
BUSINESS_FACTOR = 2.4


def _h(*parts) -> int:
    """A stable number from the parts (no random draws)."""
    return int(sha1("|".join(str(p) for p in parts).encode()).hexdigest(), 16)


def hhmm(minutes: int) -> str:
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def route_hours(from_city: str, to_city: str):
    """Flight hours for the route in either direction, or None when no flight runs."""
    return FLIGHT_HOURS.get((from_city, to_city)) or FLIGHT_HOURS.get((to_city, from_city))


def flight_no(code: str, from_city: str, to_city: str, day: str, depart: str) -> str:
    return f"{code} {100 + _h(f'{code}|{from_city}|{to_city}|{day}|{depart}') % 900}"


def _lead_factor(day: str) -> float:
    ahead = (date.fromisoformat(day) - date.fromisoformat(TODAY)).days
    return 1.6 if ahead <= 3 else 1.3 if ahead <= 7 else 1.1 if ahead < 14 else 1.0


def _time_factor(minute: int) -> float:
    if 7 * 60 <= minute < 10 * 60 or 17 * 60 <= minute < 20 * 60:
        return 1.18            # office-hour peaks cost more
    return 0.85 if minute < 6 * 60 or minute >= 21 * 60 else 1.0


def _seats(key: str) -> int:
    """One flight in five is nearly full; the rest have 10 or more seats."""
    n = _h("seats", key)
    return 1 + n % 9 if n % 5 == 0 else 10 + n % 20


def search_flights(from_city, to_city, day, pax, cabin="economy") -> list[dict]:
    """8 to 12 flights over the four carriers, sorted by departure time."""
    hours = route_hours(from_city, to_city)
    if hours is None:
        raise ValueError(f"no flights run between {from_city} and {to_city}")
    if cabin not in CABINS:
        raise ValueError("cabin must be economy or business")
    count = 8 + _h("count", from_city, to_city, day) % 5
    picked = sorted(sorted(SLOTS, key=lambda s: _h("slot", from_city, to_city, day, s))[:count])
    out = []
    for slot in picked:
        code = list(CARRIER_CODES.values())[_h("carrier", from_city, to_city, day, slot) % 4]
        carrier = next(n for n, c in CARRIER_CODES.items() if c == code)
        depart = hhmm(slot)
        key = f"{code}|{from_city}|{to_city}|{day}|{depart}"
        stops = 1 if hours >= 1.5 and _h("stops", key) % 4 == 0 else 0
        minutes = round(hours * 60 / 5) * 5 + 40 * stops
        fare = 2200 + 1700 * hours
        fare *= CARRIER_FACTOR[code] * _time_factor(slot) * _lead_factor(day) * (0.92 + (_h("jitter", key) % 17) / 100)
        fare *= 0.88 if stops else 1.0
        fare *= BUSINESS_FACTOR if cabin == "business" else 1.0
        out.append({"option_id": f"FL-{sha1(key.encode()).hexdigest()[:8]}", "carrier": carrier,
                    "flight_no": flight_no(code, from_city, to_city, day, depart), "depart_time": depart,
                    "arrive_time": hhmm(slot + minutes), "arrives_next_day": slot + minutes >= 24 * 60,
                    "cabin": cabin, "stops": stops, "fare_inr": int(round(fare / 10) * 10),
                    "seats_left": _seats(key)})
    return out


def search_hotels(city, check_in, nights, rooms) -> list[dict]:
    """Every hotel in the city with a rate for the stay. Some are above the city policy rate."""
    if city not in HOTELS:
        raise ValueError(f"no hotels listed for {city}")
    out = []
    over = min(HOTELS[city], key=lambda n: _h("over", n, city, check_in))   # at most one hotel is above the city rate
    for name in HOTELS[city]:
        key = f"{name}|{city}|{check_in}"
        above = name == over and _h("above", key) % 3 != 0
        factor = 1.05 + (_h("rate", key) % 20) / 100 if above else 0.70 + (_h("rate", key) % 31) / 100
        out.append({"option_id": f"HT-{sha1(key.encode()).hexdigest()[:8]}", "hotel": name, "city": city,
                    "rate_inr": int(round(POLICY_RATE[city] * factor / 50) * 50),
                    "stars": 3 + _h("stars", key) % 3, "km_to_center": round(0.5 + (_h("km", key) % 90) / 10, 1)})
    return out


def _day_arg(args, name):
    value = str_arg(args, name)
    try:
        if value is None or not DATE_RE.match(value):
            raise ValueError
        date.fromisoformat(value)
    except ValueError:
        raise ToolInputError(f"{name} must be a real date like 2026-10-28")
    return value


def _flights_handler(args, area_id, as_of, ctx):
    pax = int_arg(args, "pax", 1, 1, 9)
    try:
        flights = search_flights(str_arg(args, "from_city"), str_arg(args, "to_city"), _day_arg(args, "date"), pax,
                                 str_arg(args, "cabin") or "economy")
    except ValueError as exc:
        raise ToolInputError(str(exc))
    return {"flights": flights}


def _hotels_handler(args, area_id, as_of, ctx):
    try:
        hotels = search_hotels(str_arg(args, "city"), _day_arg(args, "check_in"), int_arg(args, "nights", 1, 1, 30),
                               int_arg(args, "rooms", 1, 1, 9))
    except ValueError as exc:
        raise ToolInputError(str(exc))
    return {"hotels": hotels}


def fare_tools() -> list:
    """The two read tools for the travel booking agent."""
    text = {"type": "string"}
    num = {"type": "integer"}
    return [
        build_tool("search_flights", "Search flights for one route and date (simulated fares).",
                   {"from_city": text, "to_city": text, "date": text, "pax": num, "cabin": text},
                   _flights_handler, area_ok=lambda a: a == AREA, area_label="DevX internal"),
        build_tool("search_hotels", "Search hotels in one city for a stay (simulated rates).",
                   {"city": text, "check_in": text, "nights": num, "rooms": num},
                   _hotels_handler, area_ok=lambda a: a == AREA, area_label="DevX internal"),
    ]
