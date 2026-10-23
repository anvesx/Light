"""Adds dummy business trips (fares, hotels, what was available) and the spend_advisor answer keys."""
import hashlib
import random
from datetime import date, timedelta

# The simple rules. The connector and the tests use the same numbers.
SPEND_RULES = dict(
    late_days=3,             # booked this many days or fewer before departure ...
    early_from=14,           # ... and a fare this much cheaper existed 14 to 7 days before departure
    early_to=7,
    min_saving_share=0.30,   # "much cheaper": at least 30% below what was paid
    short_flight_hours=2.5,  # business cabin on a flight shorter than this is a saving case
    same_city_days=7,        # same team, same city, departures this close could have been one trip
    hotel_over_share=0.10,   # hotel rate more than 10% above the city policy rate
)

POLICY_RATE = dict(Mumbai=7500, Delhi=7000, Bengaluru=6500, Hyderabad=5500, Chennai=5500, Pune=5000)
HOTELS = dict(
    Mumbai=["Harbour Crest Hotel", "Marine Lane Inn", "Bandra Court Suites", "Colaba Stay"],
    Delhi=["Lutyens Gate Hotel", "Connaught Rest Inn", "Aero Plaza Suites", "Saket Stay"],
    Bengaluru=["Garden City Hotel", "Indiranagar Rest Inn", "Whitefield Court", "MG Road Stay"],
    Hyderabad=["Pearl Fort Hotel", "Hitech Rest Inn", "Banjara Court", "Charminar Stay"],
    Chennai=["Marina Bay Hotel", "Anna Salai Inn", "Adyar Court Suites", "T Nagar Stay"],
    Pune=["Deccan View Hotel", "Koregaon Rest Inn", "Baner Court", "Camp Stay"])
FLIGHT_HOURS = {("Mumbai", "Bengaluru"): 2.0, ("Delhi", "Mumbai"): 2.2, ("Mumbai", "Pune"): 0.9,
                ("Hyderabad", "Mumbai"): 1.5, ("Chennai", "Mumbai"): 2.0, ("Bengaluru", "Delhi"): 2.8,
                ("Delhi", "Pune"): 2.2, ("Delhi", "Hyderabad"): 2.3, ("Chennai", "Delhi"): 2.9,
                ("Bengaluru", "Pune"): 1.5, ("Bengaluru", "Hyderabad"): 1.3, ("Bengaluru", "Chennai"): 1.0,
                ("Hyderabad", "Pune"): 1.3, ("Chennai", "Pune"): 1.8, ("Chennai", "Hyderabad"): 1.3}
TRAIN_HOURS = {("Mumbai", "Pune"): 3.5, ("Bengaluru", "Chennai"): 5.0}
FLIGHT_CARRIERS = ["Kestrel Air", "Sarang Airways", "Nimbus Jet", "Tarang Air"]
CARRIER_CODES = {"Kestrel Air": "KSA", "Sarang Airways": "SRG", "Nimbus Jet": "NMB", "Tarang Air": "TRG"}
TRAIN_CARRIERS = ["Sahyadri Express", "Malabar Link", "Gati Rail"]
CURVE_SLOPE = dict(flight=0.9, train=0.3)       # how fast a fare rises in the last 14 days
SEEN_DAYS_AHEAD = [21, 18, 15, 14, 12, 10, 8, 7, 5, 3, 2, 1]
FARE_RANGE = dict(economy=(4200, 13000), late=(5000, 13000), business=(11000, 22000), biz_cheaper=(8000, 10000),
                  train=(1400, 4200))
HOME = dict(P01="Mumbai", P02="Pune", P03="Delhi", P04="Bengaluru", P05="Pune", P06="Chennai", P30="Mumbai")
URGENT_NOTE = "Urgent client escalation: on-site fix needed, travel booked at short notice."

# One entry per trip, grouped by the existing travel expense they itemise.
# Keys: from, to, purpose, client, dep_off (days before the expense date), nights (choices), mode, tag.
T = dict
PLAN = {
    "EXP067": [T(to="Mumbai", purpose="client meeting", client="C01", dep_off=3, nights=[0], mode="flight")],
    "EXP077": [T(to="Pune", purpose="client meeting", client="C01", dep_off=2, nights=[0, 1], mode="train")],
    "EXP089": [T(to="Bengaluru", purpose="client meeting", client="C02", dep_off=4, nights=[2], mode="flight", tag="pair"),
               T(to="Mumbai", purpose="client meeting", client="C01", dep_off=13, nights=[0], mode="flight",
                 tag="biz_short")],
    "EXP090": [T(to="Bengaluru", purpose="client meeting", client="C02", dep_off=10, nights=[1], mode="flight", tag="pair"),
               T(to="Pune", purpose="client meeting", client="C01", dep_off=7, nights=[2], mode="train",
                 tag="hotel_high"),
               T(to="Hyderabad", purpose="client meeting", client="C06", dep_off=2, nights=[0], mode="flight",
                 tag="biz_short")],
    "EXP091": [T(to="Pune", purpose="client meeting", client="C03", dep_off=3, nights=[1, 2], mode="flight", tag="late")],
    "EXP105": [T(to="Pune", purpose="client meeting", client="C03", dep_off=2, nights=[0, 1], mode="flight")],
    "EXP122": [T(to="Pune", purpose="client meeting", client="C01", dep_off=2, nights=[1], mode="flight", tag="pair")],
    "EXP121": [T(to="Pune", purpose="client meeting", client="C03", dep_off=2, nights=[1, 2], mode="flight", tag="pair")],
    "EXP128": [T(to="Chennai", purpose="client meeting", client="C04", dep_off=1, nights=[0], mode="flight", tag="late")],
    "EXP132": [T(to="Delhi", purpose="client meeting", client="C05", dep_off=1, nights=[0], mode="flight", tag="late")],
    "EXP021": [T(to="Bengaluru", purpose="client meeting", client="C02", dep_off=1, nights=[1], mode="flight",
                 tag="late_urgent")],
    "EXP022": [T(to="Hyderabad", purpose="event", client=None, dep_off=3, nights=[1, 2], mode="flight")],
    "EXP027": [T(to="Pune", purpose="client meeting", client="C03", dep_off=1, nights=[1], mode="train",
                 tag="hotel_high")],
    "EXP057": [T(to="Bengaluru", purpose="event", client=None, dep_off=0, nights=[0], mode="flight",
                 tag="biz_cheaper")],
    "EXP063": [T(to="Hyderabad", purpose="internal", client=None, dep_off=2, nights=[1, 2], mode="flight")],
}
# Pairs that could have been one trip: the two trips share a pair tag inside one team (checked by the rule below).


def D(s):
    return date.fromisoformat(s)


def round_to(x, n):
    return int(round(x / n) * n)


def curve(mode, days_ahead):
    """Fare multiplier by how many days before departure the fare is seen: 1.0 at 14+ days, rising after."""
    return 1.0 + CURVE_SLOPE[mode] * max(0, 14 - days_ahead) / 14


def hours_of(mode, a, b):
    table = FLIGHT_HOURS if mode == "flight" else TRAIN_HOURS
    return table.get((a, b)) or table[(b, a)]


# ---- the rules (the answer key and the tests use these) ------------------------------------------------------

def late_booking(trip, options):
    """Saving for a late booking, or None. options: fare options of this trip."""
    R = SPEND_RULES
    ahead = (D(trip["depart_on"]) - D(trip["booked_on"])).days
    if ahead > R["late_days"] or "urgent" in (trip["note"] or "").lower():
        return None
    early = [o for o in options if o["mode"] == trip["mode"] and o["cabin"] == trip["cabin"]
             and R["early_to"] <= (D(trip["depart_on"]) - D(o["seen_on"])).days <= R["early_from"]]
    if not early:
        return None
    best = min(early, key=lambda o: (o["fare_inr"], o["seen_on"], o["option_id"]))
    saving = trip["fare_inr"] - best["fare_inr"]
    if saving < R["min_saving_share"] * trip["fare_inr"]:
        return None
    return dict(rule="late_booking", trip_id=trip["trip_id"], date=trip["depart_on"], paid_inr=trip["fare_inr"],
                cheaper_inr=best["fare_inr"], saving_inr=saving, option_id=best["option_id"], seen_on=best["seen_on"],
                carrier=best["carrier"], booked_days_before=ahead)


def business_short(trip, options):
    """Saving for a business seat on a short flight, or None: the cheapest economy fare seen on the booking day."""
    if trip["mode"] != "flight" or trip["cabin"] != "business" or trip["duration_hours"] >= SPEND_RULES["short_flight_hours"]:
        return None
    same_day = [o for o in options if o["mode"] == "flight" and o["cabin"] == "economy" and o["seen_on"] == trip["booked_on"]]
    if not same_day:
        return None
    best = min(same_day, key=lambda o: (o["fare_inr"], o["option_id"]))
    if best["fare_inr"] >= trip["fare_inr"]:
        return None
    return dict(rule="business_short_flight", trip_id=trip["trip_id"], date=trip["depart_on"], paid_inr=trip["fare_inr"],
                cheaper_inr=best["fare_inr"], saving_inr=trip["fare_inr"] - best["fare_inr"], option_id=best["option_id"],
                seen_on=best["seen_on"], carrier=best["carrier"], duration_hours=trip["duration_hours"])


def same_city_pairs(trips):
    """Pairs of trips by one team to one city, departing within the window. The saving is the lower fare."""
    out = []
    ordered = sorted(trips, key=lambda t: (t["depart_on"], t["trip_id"]))
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            gap = (D(b["depart_on"]) - D(a["depart_on"])).days
            if gap > SPEND_RULES["same_city_days"]:
                break
            if a["team"] == b["team"] and a["to_city"] == b["to_city"]:
                low = min(a["fare_inr"], b["fare_inr"])
                out.append(dict(rule="same_city_trips", trip_id=b["trip_id"], other_trip_id=a["trip_id"],
                                date=b["depart_on"], other_date=a["depart_on"], city=b["to_city"], team=b["team"],
                                paid_inr=a["fare_inr"] + b["fare_inr"], saving_inr=low, gap_days=gap))
    return out


def hotel_over_policy(stay, policy_rate, alternatives, depart_on):
    """Saving for a hotel above the city rate, or None. The saving is the extra cost over the policy rate."""
    if stay["rate_inr"] <= policy_rate * (1 + SPEND_RULES["hotel_over_share"]):
        return None
    cheapest = min(alternatives, key=lambda o: (o["rate_inr"], o["option_id"])) if alternatives else None
    return dict(rule="hotel_above_city_rate", trip_id=stay["trip_id"], date=depart_on, city=stay["city"],
                hotel=stay["hotel"], nights=stay["nights"], rate_inr=stay["rate_inr"], policy_rate_inr=policy_rate,
                paid_inr=stay["total_inr"], saving_inr=(stay["rate_inr"] - policy_rate) * stay["nights"],
                cheaper_hotel=cheapest["hotel"] if cheapest else None,
                cheaper_rate_inr=cheapest["rate_inr"] if cheapest else None)


# ---- the generator -------------------------------------------------------------------------------------------

def fare_limits(spec, tag):
    if tag == "biz_short":
        return FARE_RANGE["business"]
    if tag == "biz_cheaper":
        return FARE_RANGE["biz_cheaper"]
    if spec["mode"] == "train":
        return FARE_RANGE["train"]
    return FARE_RANGE["late"] if tag in ("late", "late_urgent") else FARE_RANGE["economy"]


def solve_trip_money(rng, amount, specs):
    """Pick nights, hotel rate and fare for each trip so that fares plus hotels equal the expense amount exactly."""
    for _ in range(20000):
        parts, total = [], 0
        for i, s in enumerate(specs):
            nights = rng.choice(s["nights"])
            policy = POLICY_RATE[s["to"]]
            high = s.get("tag") == "hotel_high"
            rate = round_to(policy * (rng.uniform(1.3, 1.5) if high else rng.uniform(0.6, 1.0)), 50) if nights else 0
            lo, hi = fare_limits(s, s.get("tag"))
            fare = amount - total - nights * rate if i == len(specs) - 1 else round_to(rng.uniform(lo, hi), 10)
            total += fare + nights * rate
            parts.append((nights, rate, fare))
        if all(fare_limits(s, s.get("tag"))[0] <= p[2] <= fare_limits(s, s.get("tag"))[1] for s, p in zip(specs, parts)):
            return parts
    raise AssertionError(f"no trip split found for {amount}")


def add_trips(b, seed):
    rng = random.Random(seed + 13)
    rows = b.rows
    expense = {e["expense_id"]: e for e in rows["expenses"]}
    trips, stays, fare_opts, hotel_opts = [], [], [], []
    tags = {}

    for exp_id in sorted(PLAN, key=lambda k: expense[k]["date"]):
        e = expense[exp_id]
        specs = [dict(s, **{"from": HOME[e["person_id"]]}) for s in PLAN[exp_id]]
        parts = solve_trip_money(rng, e["amount_inr"], specs)
        for s, (nights, rate, fare) in zip(specs, parts):
            depart = D(e["date"]) - timedelta(days=s["dep_off"])
            assert nights <= s["dep_off"], (exp_id, nights, s["dep_off"])
            tag = s.get("tag")
            d_book = rng.randint(1, 3) if tag == "late" else 1 if tag == "late_urgent" else \
                rng.randint(9, 14) if tag in ("biz_short", "biz_cheaper") else rng.randint(8, 20)
            cabin = "business" if tag in ("biz_short", "biz_cheaper") else "economy"
            carrier = rng.choice(FLIGHT_CARRIERS if s["mode"] == "flight" else TRAIN_CARRIERS)
            trip = dict(trip_id="", person_id=e["person_id"], team=e["team"], purpose=s["purpose"],
                        client_id=s["client"], from_city=s["from"], to_city=s["to"], depart_on=depart.isoformat(),
                        return_on=(depart + timedelta(days=nights)).isoformat(),
                        booked_on=(depart - timedelta(days=d_book)).isoformat(), mode=s["mode"], carrier=carrier,
                        cabin=cabin, fare_inr=fare, expense_id=exp_id, duration_hours=hours_of(s["mode"], s["from"], s["to"]),
                        note=URGENT_NOTE if tag == "late_urgent" else None)
            trips.append((trip, s, nights, rate, d_book))
    trips.sort(key=lambda x: (x[0]["depart_on"], x[0]["expense_id"]))

    out_trips, counters = [], dict(FO=0, HS=0, HO=0)
    for n, (trip, s, nights, rate, d_book) in enumerate(trips, 1):
        trip["trip_id"] = f"TR{n:03d}"
        tag = s.get("tag")
        tags[trip["trip_id"]] = tag
        b.add("trips", **trip)
        out_trips.append(trip)
        _add_fare_options(b, rng, trip, d_book, tag, counters, fare_opts)
        if nights:
            _add_stay(b, rng, trip, nights, rate, tag, counters, stays, hotel_opts)
    for city, rate in POLICY_RATE.items():
        b.add("city_hotel_rates", city=city, policy_rate_inr=rate)

    _add_flight_numbers(b)
    b.keys["spend_advisor"] = _answer_key(out_trips, fare_opts, stays, hotel_opts, tags)


def flight_number(carrier, key):
    """C9: carrier code plus 100 + sha1(key) mod 900. Trains have no code, so they get None."""
    code = CARRIER_CODES.get(carrier)
    return f"{code} {100 + int(hashlib.sha1(key.encode()).hexdigest(), 16) % 900}" if code else None


def _clock_after(hhmm, hours):
    mins = (int(hhmm[:2]) * 60 + int(hhmm[3:]) + round(hours * 60)) % 1440
    return f"{mins // 60:02d}:{mins % 60:02d}"


def _add_flight_numbers(b):
    """Flight numbers and arrive times from hashes only (no random draws). A trip takes its paid option's number."""
    by_trip = {t["trip_id"]: t for t in b.rows["trips"]}
    for o in b.rows["fare_options"]:
        t = by_trip[o["trip_id"]]
        o["flight_no"] = flight_number(o["carrier"], o["option_id"])
        o["arrive_time"] = _clock_after(o["depart_time"], t["duration_hours"])
    for t in b.rows["trips"]:
        paid = [o for o in b.rows["fare_options"] if o["trip_id"] == t["trip_id"] and o["carrier"] == t["carrier"]
                and o["cabin"] == t["cabin"] and o["fare_inr"] == t["fare_inr"] and o["seen_on"] == t["booked_on"]]
        assert paid, t["trip_id"]
        t["depart_time"], t["flight_no"] = paid[0]["depart_time"], paid[0]["flight_no"]


def _add_fare_options(b, rng, trip, d_book, tag, counters, fare_opts):
    """Fares seen from 21 days out up to the booking day. The paid fare appears on the booking day."""
    mode, depart = trip["mode"], D(trip["depart_on"])
    base = trip["fare_inr"] / curve(mode, d_book)
    carriers = FLIGHT_CARRIERS if mode == "flight" else TRAIN_CARRIERS
    others = rng.sample([c for c in carriers if c != trip["carrier"]], 2)
    factor = {trip["carrier"]: 1.0, others[0]: rng.uniform(1.0, 1.10), others[1]: rng.uniform(1.0, 1.10)}  # paid fare is the cheapest that day
    cabins = [trip["cabin"]] + (["economy"] if trip["cabin"] == "business" else [])
    for ahead in sorted({d for d in SEEN_DAYS_AHEAD if d >= d_book} | {d_book}, reverse=True):
        seen = (depart - timedelta(days=ahead)).isoformat()
        for cabin in cabins:
            for carrier in [trip["carrier"]] + others:
                if cabin != trip["cabin"]:   # economy seats next to a business trip
                    ratio = rng.uniform(0.36, 0.46)
                    if tag == "biz_cheaper" and ahead == d_book:
                        ratio = rng.uniform(1.25, 1.4)   # economy was nearly sold out that day
                    price = round_to(base * ratio * curve(mode, ahead) * factor[carrier], 10)
                elif carrier == trip["carrier"] and ahead == d_book:
                    price = trip["fare_inr"]
                else:
                    price = round_to(base * curve(mode, ahead) * factor[carrier] * rng.uniform(1.0, 1.03), 10)
                counters["FO"] += 1
                row = dict(option_id=f"FO{counters['FO']:04d}", trip_id=trip["trip_id"], seen_on=seen, carrier=carrier,
                           mode=mode, cabin=cabin, depart_time=f"{rng.choice([6, 7, 8, 9, 11, 14, 17, 19]):02d}:{rng.choice(['00', '15', '30', '45'])}",
                           fare_inr=price)
                b.add("fare_options", **row)
                fare_opts.append(row)


def _add_stay(b, rng, trip, nights, rate, tag, counters, stays, hotel_opts):
    city = trip["to_city"]
    names = rng.sample(HOTELS[city], 3)
    counters["HS"] += 1
    stay = dict(stay_id=f"HS{counters['HS']:03d}", trip_id=trip["trip_id"], city=city, hotel=names[0], nights=nights,
                rate_inr=rate, total_inr=nights * rate)
    b.add("hotel_stays", **stay)
    stays.append(stay)
    policy = POLICY_RATE[city]
    if tag == "hotel_high":   # a hotel within the city rate was available
        alts = [round_to(policy * rng.uniform(0.6, 0.95), 50) for _ in names[1:]]
    else:                     # the chosen hotel is the cheapest option
        alts = [round_to(rate * rng.uniform(1.0, 1.25), 50) for _ in names[1:]]
    for name, r in zip(names, [rate] + alts):
        counters["HO"] += 1
        row = dict(option_id=f"HO{counters['HO']:04d}", stay_id=stay["stay_id"], hotel=name, rate_inr=r)
        b.add("hotel_options", **row)
        hotel_opts.append(row)


def _answer_key(trips, fare_opts, stays, hotel_opts, tags):
    by_trip = {t["trip_id"]: t for t in trips}
    opts = {}
    for o in fare_opts:
        opts.setdefault(o["trip_id"], []).append(o)
    found = []
    for t in trips:
        found += [x for x in (late_booking(t, opts[t["trip_id"]]), business_short(t, opts[t["trip_id"]])) if x]
    found += same_city_pairs(trips)
    for s in stays:
        alts = [o for o in hotel_opts if o["stay_id"] == s["stay_id"] and o["hotel"] != s["hotel"]]
        x = hotel_over_policy(s, POLICY_RATE[s["city"]], alts, by_trip[s["trip_id"]]["depart_on"])
        if x:
            found.append(x)
    want = {(x["rule"], x["trip_id"]) for x in found}
    planted = {("late_booking", t) for t, g in tags.items() if g == "late"}
    planted |= {("business_short_flight", t) for t, g in tags.items() if g == "biz_short"}
    planted |= {("hotel_above_city_rate", t) for t, g in tags.items() if g == "hotel_high"}
    planted |= {("same_city_trips", x["trip_id"]) for x in same_city_pairs(trips)}
    assert want == planted and len(planted) == 9, (want ^ planted)
    cases, n = [], 0
    for x in sorted(found, key=lambda x: (x["date"], x["rule"], x["trip_id"])):
        n += 1
        ids = [x["trip_id"]] + ([x["other_trip_id"]] if "other_trip_id" in x else [])
        cases.append(dict(case_id=f"SPD-{n}", signal=x["rule"], trip_ids=ids, first_detectable_on=x["date"],
                          paid_inr=x["paid_inr"], saving_inr=x["saving_inr"]))
    urgent = [t for t, g in tags.items() if g == "late_urgent"][0]
    cheaper = [t for t, g in tags.items() if g == "biz_cheaper"][0]
    look = [dict(case_id="SPD-L1", signal="late_booking_urgent", trip_ids=[urgent], first_detectable_on=by_trip[urgent]["depart_on"],
                 note="booked one day ahead for an urgent client escalation: the purpose note says urgent"),
            dict(case_id="SPD-L2", signal="business_cheaper_than_economy", trip_ids=[cheaper],
                 first_detectable_on=by_trip[cheaper]["depart_on"],
                 note="a business seat on a short flight, but every economy seat cost more that day")]
    return dict(cases=cases, look_alikes=look, rules=SPEND_RULES)
