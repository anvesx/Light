"""Read tools for the spend advisor: company cost by category, trip savings and verdicts, travel by team. Team totals only."""
import json
from pathlib import Path

from .tool_reply import DATE_RE, ToolInputError, build_tool, days_before, days_between, str_arg

AREA = "devx-internal"
DEFAULT_DAYS = 90
SALARY_MONTH_DAYS = 30
POLICY = json.loads((Path(__file__).resolve().parents[2] / "agents" / "finance" / "travel_booking" / "travel_policy.json").read_text())
LATE_DAYS, EARLY_FROM, EARLY_TO = POLICY["late_booking_days"], 14, 7   # a cheaper fare 14 to 7 days before is "earlier"
MIN_SAVING_SHARE = POLICY["earlier_fare_min_saving_share"]             # "much cheaper": 30% or more below what was paid
SHORT_FLIGHT_HOURS = POLICY["economy_only_under_hours"]
SAME_CITY_DAYS = POLICY["same_city_days"]
MAX_OPTIONS = 3
HOTEL_OVER_SHARE = POLICY["hotel_over_city_rate_share"]
RULES = ("late_booking", "business_short_flight", "same_city_trips", "hotel_above_city_rate")


def _ok(area_id):
    return area_id == AREA


def _date_arg(args, name):
    value = str_arg(args, name)
    if value is not None and not DATE_RE.match(value):
        raise ToolInputError(f"{name} must look like YYYY-MM-DD")
    return value


def _window(args, as_of):
    """The from and to dates: to is never after as_of; from defaults to 90 days before to."""
    end = min(_date_arg(args, "to") or as_of, as_of)
    start = _date_arg(args, "from") or days_before(end, DEFAULT_DAYS)
    if start > end:
        raise ToolInputError("from is after to")
    return start, end


def _pct(part, whole):
    return round(part * 100 / whole, 1) if whole else 0.0


def _rows(conn, sql, *params):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


# ---- cost by category ------------------------------------------------------------------------------------------

def _breakdown(conn, start, end):
    days = days_between(end, start) + 1
    pay = conn.execute("SELECT COALESCE(SUM(monthly_salary_inr), 0) FROM people WHERE is_devx = 1").fetchone()[0]
    items = [("salaries", "Salaries, all teams", round(pay * days / SALARY_MONTH_DAYS))]
    for r in _rows(conn, "SELECT v.category AS c, SUM(i.amount_inr) AS s FROM invoices i JOIN vendors v USING(vendor_id) "
                         "WHERE i.date BETWEEN ? AND ? GROUP BY v.category", start, end):
        items.append(("vendor_invoices", f"Vendor invoices: {r['c']}", r["s"]))
    travel = 0
    for r in _rows(conn, "SELECT category AS c, SUM(amount_inr) AS s FROM expenses WHERE date BETWEEN ? AND ? "
                         "GROUP BY category", start, end):
        if r["c"] == "travel":
            travel = r["s"]
        else:
            items.append(("expenses", f"Expenses: {r['c']}", r["s"]))
    legs = conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN t.mode = 'flight' THEN t.fare_inr END), 0), "
        "COALESCE(SUM(CASE WHEN t.mode = 'train' THEN t.fare_inr END), 0) FROM trips t JOIN expenses e USING(expense_id) "
        "WHERE e.date BETWEEN ? AND ?", (start, end)).fetchone()
    hotels = conn.execute("SELECT COALESCE(SUM(h.total_inr), 0) FROM hotel_stays h JOIN trips t USING(trip_id) "
                          "JOIN expenses e USING(expense_id) WHERE e.date BETWEEN ? AND ?", (start, end)).fetchone()[0]
    other = travel - legs[0] - legs[1] - hotels
    for key, label, amount in (("flights", "Travel: flights", legs[0]), ("trains", "Travel: trains", legs[1]),
                               ("hotels", "Travel: hotels", hotels), ("other_travel", "Travel: local and other", other)):
        if amount:
            items.append((key, label, amount))
    total = sum(a for _, _, a in items)
    cats = [{"key": k, "label": label, "amount_inr": a, "share_pct": _pct(a, total)}
            for k, label, a in sorted(items, key=lambda x: (-x[2], x[1]))]
    salaries = items[0][2]
    travel_block = {"total_inr": travel, "share_pct": _pct(travel, total),
                    "share_of_non_salary_pct": _pct(travel, total - salaries),
                    "flights_inr": legs[0], "flights_share_pct": _pct(legs[0], total),
                    "trains_inr": legs[1], "trains_share_pct": _pct(legs[1], total),
                    "hotels_inr": hotels, "hotels_share_pct": _pct(hotels, total),
                    "other_inr": other, "other_share_pct": _pct(other, total)}
    return {"from": start, "to": end, "total_inr": total, "categories": cats, "travel": travel_block}


def make_spend_breakdown(data_conn):
    def handler(args, area_id, as_of, ctx):
        start, end = _window(args, as_of)
        return _breakdown(data_conn, start, end)
    return build_tool(
        "spend_breakdown", "Company cost from `from` to `to` (default: last 90 days to as_of) by category: salaries as one total, "
        "vendor invoices by category, expenses by category, and travel split into flights, trains and hotels. "
        "Each with amount and share of the total.", {"from": {"type": "string"}, "to": {"type": "string"}},
        handler, area_ok=_ok, area_label=AREA)


# ---- trip savings ----------------------------------------------------------------------------------------------

def _all_savings(conn, as_of):
    """Every saving on trips that departed by as_of. Each has rule, trip_id, date, paid_inr, saving_inr and the facts."""
    trips = _rows(conn, "SELECT * FROM trips WHERE depart_on <= ? ORDER BY depart_on, trip_id", as_of)
    fares = {}
    for o in _rows(conn, "SELECT o.* FROM fare_options o JOIN trips t USING(trip_id) WHERE t.depart_on <= ?", as_of):
        fares.setdefault(o["trip_id"], []).append(o)
    out = []
    for t in trips:
        opts = fares.get(t["trip_id"], [])
        ahead = days_between(t["depart_on"], t["booked_on"])
        early = _late_options(t, opts)
        if ahead <= LATE_DAYS and "urgent" not in (t["note"] or "").lower() and early:
            best = min(early, key=lambda o: (o["fare_inr"], o["seen_on"], o["option_id"]))
            if t["fare_inr"] - best["fare_inr"] >= MIN_SAVING_SHARE * t["fare_inr"]:
                out.append({"rule": "late_booking", "trip_id": t["trip_id"], "team": t["team"], "date": t["depart_on"],
                            "paid_inr": t["fare_inr"], "cheaper_inr": best["fare_inr"],
                            "saving_inr": t["fare_inr"] - best["fare_inr"], "available_on": best["seen_on"],
                            "carrier": best["carrier"], "booked_on": t["booked_on"], "booked_days_before": ahead,
                            "to_city": t["to_city"]})
        if t["mode"] == "flight" and t["cabin"] == "business" and t["duration_hours"] < SHORT_FLIGHT_HOURS:
            econ = _economy_options(t, opts)
            best = min(econ, key=lambda o: (o["fare_inr"], o["option_id"])) if econ else None
            if best and best["fare_inr"] < t["fare_inr"]:
                out.append({"rule": "business_short_flight", "trip_id": t["trip_id"], "team": t["team"],
                            "date": t["depart_on"], "paid_inr": t["fare_inr"], "cheaper_inr": best["fare_inr"],
                            "saving_inr": t["fare_inr"] - best["fare_inr"], "available_on": best["seen_on"],
                            "carrier": best["carrier"], "flight_hours": t["duration_hours"], "to_city": t["to_city"]})
    for i, a in enumerate(trips):
        for b in trips[i + 1:]:
            if days_between(b["depart_on"], a["depart_on"]) > SAME_CITY_DAYS:
                break
            if a["team"] == b["team"] and a["to_city"] == b["to_city"]:
                out.append({"rule": "same_city_trips", "trip_id": b["trip_id"], "other_trip_id": a["trip_id"],
                            "team": b["team"], "date": b["depart_on"], "other_date": a["depart_on"],
                            "paid_inr": a["fare_inr"] + b["fare_inr"], "saving_inr": min(a["fare_inr"], b["fare_inr"]),
                            "cheaper_inr": max(a["fare_inr"], b["fare_inr"]), "to_city": b["to_city"]})
    for s in _rows(conn, "SELECT s.*, t.depart_on, t.team, c.policy_rate_inr FROM hotel_stays s JOIN trips t USING(trip_id) "
                         "JOIN city_hotel_rates c USING(city) WHERE t.depart_on <= ?", as_of):
        if s["rate_inr"] > s["policy_rate_inr"] * (1 + HOTEL_OVER_SHARE):
            alts = _rows(conn, "SELECT * FROM hotel_options WHERE stay_id = ? AND hotel != ? ORDER BY rate_inr, option_id",
                         s["stay_id"], s["hotel"])
            out.append({"rule": "hotel_above_city_rate", "trip_id": s["trip_id"], "team": s["team"],
                        "date": s["depart_on"], "paid_inr": s["total_inr"], "city": s["city"], "nights": s["nights"],
                        "rate_inr": s["rate_inr"], "policy_rate_inr": s["policy_rate_inr"],
                        "saving_inr": (s["rate_inr"] - s["policy_rate_inr"]) * s["nights"],
                        "cheaper_inr": s["policy_rate_inr"] * s["nights"],
                        "cheaper_hotel": alts[0]["hotel"] if alts else None,
                        "cheaper_hotel_rate_inr": alts[0]["rate_inr"] if alts else None})
    return sorted(out, key=lambda x: (-x["saving_inr"], x["date"], x["trip_id"], x["rule"]))


def _late_options(t, opts):
    """Same mode and cabin, seen 14 to 7 days before departure and not after the booking day."""
    return [o for o in opts if o["mode"] == t["mode"] and o["cabin"] == t["cabin"] and o["seen_on"] <= t["booked_on"]
            and EARLY_TO <= days_between(t["depart_on"], o["seen_on"]) <= EARLY_FROM]


def _economy_options(t, opts):
    """Economy flights seen on the booking day."""
    return [o for o in opts if o["mode"] == "flight" and o["cabin"] == "economy" and o["seen_on"] == t["booked_on"]]


RULE_TEXT = {
    "late_booking": "Book at least 7 days ahead. A cheaper fare was open 14 to 7 days before departure.",
    "business_short_flight": "Use economy on flights under 2.5 hours.",
    "hotel_above_city_rate": "Keep hotels at or under the city rate.",
    "same_city_trips": "Merge trips by one team to the same city within a week.",
}


def _flight_option(o, paid, rule):
    return {"carrier": o["carrier"], "flight_no": o["flight_no"], "depart_time": o["depart_time"],
            "arrive_time": o["arrive_time"], "cabin": o["cabin"], "fare_inr": o["fare_inr"], "seen_on": o["seen_on"],
            "saving_inr": paid - o["fare_inr"], "rule": rule}


def _trip_card(conn, t, opts, found):
    rules = {x["rule"] for x in found}
    flights = []
    if "late_booking" in rules:
        flights += [_flight_option(o, t["fare_inr"], "late_booking") for o in _late_options(t, opts) if o["fare_inr"] < t["fare_inr"]]
    if "business_short_flight" in rules:
        flights += [_flight_option(o, t["fare_inr"], "business_short_flight") for o in _economy_options(t, opts)
                    if o["fare_inr"] < t["fare_inr"]]
    for x in found:   # same-city trips: the other trip's flight already covers the visit
        other = conn.execute("SELECT * FROM trips WHERE trip_id = ?", (x.get("other_trip_id"),)).fetchone()
        if x["rule"] == "same_city_trips" and other:
            flights.append({"carrier": other["carrier"], "flight_no": other["flight_no"], "depart_time": other["depart_time"],
                            "arrive_time": None, "cabin": other["cabin"], "fare_inr": other["fare_inr"],
                            "seen_on": other["booked_on"], "saving_inr": x["saving_inr"], "rule": "same_city_trips",
                            "other_trip_id": other["trip_id"]})
    flights.sort(key=lambda x: (x["fare_inr"], x["seen_on"], x["flight_no"]))
    stay = conn.execute("SELECT * FROM hotel_stays WHERE trip_id = ?", (t["trip_id"],)).fetchone()
    hotel_paid, hotels = None, []
    if stay:
        hotel_paid = {"hotel": stay["hotel"], "rate_inr": stay["rate_inr"], "nights": stay["nights"]}
        if "hotel_above_city_rate" in rules:
            alts = _rows(conn, "SELECT hotel, rate_inr FROM hotel_options WHERE stay_id = ? AND hotel != ? AND rate_inr < ? "
                               "ORDER BY rate_inr, hotel", stay["stay_id"], stay["hotel"], stay["rate_inr"])
            hotels = [{"hotel": a["hotel"], "rate_inr": a["rate_inr"],
                       "saving_inr": (stay["rate_inr"] - a["rate_inr"]) * stay["nights"], "rule": "hotel_above_city_rate"}
                      for a in alts]
    return {"trip_id": t["trip_id"], "team": t["team"], "route": f"{t['from_city']} to {t['to_city']}",
            "depart_on": t["depart_on"], "verdict": "cheaper_option_existed" if rules else "best_option_chosen",
            "rules": [{"rule": r, "text": RULE_TEXT[r]} for r in sorted(rules) if r in RULE_TEXT],
            "paid": {"carrier": t["carrier"], "flight_no": t["flight_no"], "depart_time": t["depart_time"],
                     "cabin": t["cabin"], "fare_inr": t["fare_inr"], "booked_on": t["booked_on"]},
            "hotel_paid": hotel_paid, "cheaper_flights": flights[:MAX_OPTIONS], "cheaper_hotels": hotels[:MAX_OPTIONS]}


def make_trip_alternatives(data_conn):
    def handler(args, area_id, as_of, ctx):
        trip_id = str_arg(args, "trip_id")
        start, end = ("2000-01-01", as_of) if trip_id else _window(args, as_of)
        rules = {}
        for x in _savings_in(data_conn, start, end, as_of):
            rules.setdefault(x["trip_id"], []).append(x)
        sql, params = "SELECT * FROM trips WHERE depart_on BETWEEN ? AND ?", [start, end]
        if trip_id:
            sql, params = sql + " AND trip_id = ?", params + [trip_id]
        cards = []
        for t in _rows(data_conn, sql + " ORDER BY depart_on, trip_id", *params):
            opts = _rows(data_conn, "SELECT * FROM fare_options WHERE trip_id = ?", t["trip_id"])
            cards.append(_trip_card(data_conn, t, opts, rules.get(t["trip_id"], [])))
        return {"from": start, "to": end, "trips": cards}
    return build_tool(
        "trip_alternatives", "The real cheaper flights and hotels for each trip that left from `from` to `to` (default: last 90 "
        "days to as_of), or for one `trip_id`. Each trip shows what was paid, up to 3 cheaper flights (carrier, flight number, "
        "times, fare, saving) and up to 3 cheaper hotels (name, rate, saving), cheapest first, with the policy rule. No names.",
        {"from": {"type": "string"}, "to": {"type": "string"}, "trip_id": {"type": "string"}},
        handler, area_ok=_ok, area_label=AREA)


def _savings_in(conn, start, end, as_of):
    return [x for x in _all_savings(conn, as_of) if start <= x["date"] <= end]


def make_trip_savings(data_conn):
    def handler(args, area_id, as_of, ctx):
        start, end = _window(args, as_of)
        found = _savings_in(data_conn, start, end, as_of)
        by_rule = {r: {"count": sum(x["rule"] == r for x in found),
                       "saving_inr": sum(x["saving_inr"] for x in found if x["rule"] == r)} for r in RULES}
        return {"from": start, "to": end, "total_saving_inr": sum(x["saving_inr"] for x in found), "by_rule": by_rule,
                "savings": found}
    return build_tool(
        "trip_savings", "Savings found on trips that left from `from` to `to` (default: last 90 days to as_of). Each has the trip id, "
        "date, what was paid, the cheaper option and when it was available, the amount that could have been saved and the "
        "rule. Rules: late_booking, business_short_flight, same_city_trips, hotel_above_city_rate. A late booking marked "
        "urgent is not a saving.", {"from": {"type": "string"}, "to": {"type": "string"}},
        handler, area_ok=_ok, area_label=AREA)


def make_trip_verdicts(data_conn):
    def handler(args, area_id, as_of, ctx):
        trip_id = str_arg(args, "trip_id")
        if trip_id:
            start, end = "2000-01-01", as_of
        else:
            start, end = _window(args, as_of)
        sql = ("SELECT t.trip_id, t.depart_on AS date, t.fare_inr + COALESCE((SELECT SUM(total_inr) FROM hotel_stays h "
               "WHERE h.trip_id = t.trip_id), 0) AS cost_inr FROM trips t WHERE t.depart_on BETWEEN ? AND ?")
        params = [start, end]
        if trip_id:
            sql, params = sql + " AND t.trip_id = ?", params + [trip_id]
        saved = {}
        for x in _savings_in(data_conn, start, end, as_of):
            saved.setdefault(x["trip_id"], []).append(x)
        trips = []
        for r in _rows(data_conn, sql + " ORDER BY t.depart_on, t.trip_id", *params):
            mine = saved.get(r["trip_id"], [])
            trips.append({**r, "verdict": "cheaper_option_existed" if mine else "best_option_chosen",
                          "saving_inr": sum(x["saving_inr"] for x in mine), "rules": sorted({x["rule"] for x in mine})})
        cheaper = [t for t in trips if t["saving_inr"]]
        return {"from": start, "to": end, "trip_count": len(trips), "best_option_count": len(trips) - len(cheaper),
                "cheaper_option_count": len(cheaper), "total_saving_inr": sum(t["saving_inr"] for t in cheaper),
                "trips": trips}
    return build_tool(
        "trip_verdicts", "A verdict for every trip that left from `from` to `to` (default: last 90 days to as_of), or for one "
        "`trip_id`: cheaper_option_existed (with the saving and rules) or best_option_chosen (no cheaper fare or hotel "
        "was available at booking time). Also the counts and total saving.",
        {"from": {"type": "string"}, "to": {"type": "string"}, "trip_id": {"type": "string"}},
        handler, area_ok=_ok, area_label=AREA)


# ---- travel by team --------------------------------------------------------------------------------------------

def make_travel_by_team(data_conn):
    def handler(args, area_id, as_of, ctx):
        start, end = _window(args, as_of)
        teams = _rows(data_conn,
                      "SELECT e.team, SUM(e.amount_inr) AS travel_inr, "
                      "COALESCE(SUM((SELECT SUM(fare_inr) FROM trips t WHERE t.expense_id = e.expense_id AND t.mode = 'flight')), 0) AS flights_inr, "
                      "COALESCE(SUM((SELECT SUM(fare_inr) FROM trips t WHERE t.expense_id = e.expense_id AND t.mode = 'train')), 0) AS trains_inr, "
                      "COALESCE(SUM((SELECT SUM(h.total_inr) FROM hotel_stays h JOIN trips t USING(trip_id) "
                      "WHERE t.expense_id = e.expense_id)), 0) AS hotels_inr, "
                      "COALESCE(SUM((SELECT COUNT(*) FROM trips t WHERE t.expense_id = e.expense_id)), 0) AS trips "
                      "FROM expenses e WHERE e.category = 'travel' AND e.date BETWEEN ? AND ? GROUP BY e.team "
                      "ORDER BY travel_inr DESC, e.team", start, end)
        total = sum(t["travel_inr"] for t in teams)
        for t in teams:
            t["other_inr"] = t["travel_inr"] - t["flights_inr"] - t["trains_inr"] - t["hotels_inr"]
            t["share_of_travel_pct"] = _pct(t["travel_inr"], total)
        return {"from": start, "to": end, "travel_total_inr": total, "teams": teams}
    return build_tool(
        "travel_by_team", "Travel cost per team from `from` to `to` (default: last 90 days to as_of): total, flights, trains, "
        "hotels, other, trip count and share of all travel. Team totals only.",
        {"from": {"type": "string"}, "to": {"type": "string"}}, handler, area_ok=_ok, area_label=AREA)


def spend_tools(data_conn):
    return [make_spend_breakdown(data_conn), make_trip_savings(data_conn), make_trip_verdicts(data_conn),
            make_travel_by_team(data_conn), make_trip_alternatives(data_conn)]
