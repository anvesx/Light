"""Deterministic stand-in for the model: writes the finance answer letter from the computed facts, in plain words."""
import json

from contract.types import ModelReply

from .pack import BEST_PHRASE, MARKER, inr


def _clock(hhmm):
    h = int(hhmm[:2])
    return f"{(h % 12) or 12}:{hhmm[3:5]} {'AM' if h < 12 else 'PM'}"


def _seen(day):
    return f"{('Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec')[int(day[5:7]) - 1]} {int(day[8:])}"


def _option(x):
    o = x.get("option")
    if not o:
        return ""
    if o["kind"] == "hotel":
        return f" A cheaper hotel: {o['hotel']} at {inr(o['rate_inr'])} a night."
    return (f" A cheaper flight: {o['carrier']} {o['flight_no']} at {_clock(o['depart_time'])}, {inr(o['fare_inr'])}, "
            f"seen {_seen(o['seen_on'])}.")


def _line(x):
    return _base_line(x) + _option(x)


def _base_line(x):
    head = f"{x['trip_id']} ({x['date']}): "
    if x["rule"] == "late_booking":
        days = x["booked_days_before"]
        return (head + f"The flight to {x['to_city']} was booked {days} day{'s' if days != 1 else ''} before it left and cost "
                f"{inr(x['paid_inr'])}. A similar flight cost {inr(x['cheaper_inr'])} on {x['available_on']}. "
                f"Booking a week earlier would have saved {inr(x['saving_inr'])}.")
    if x["rule"] == "business_short_flight":
        return (head + f"A business seat on a {x['flight_hours']} hour flight to {x['to_city']} cost {inr(x['paid_inr'])}. "
                f"An economy seat cost {inr(x['cheaper_inr'])} that day. Economy would have saved {inr(x['saving_inr'])}.")
    if x["rule"] == "same_city_trips":
        return (head + f"The {x['team'].replace('_', ' ')} team also sent {x['other_trip_id']} ({x['other_date']}) to "
                f"{x['to_city']}, within 7 days. One trip could have done both. The lower fare, {inr(x['saving_inr'])}, "
                "would have been saved.")
    return (head + f"The hotel in {x['city']} cost {inr(x['rate_inr'])} a night. The city rate is {inr(x['policy_rate_inr'])}. "
            f"{x['nights']} night{'s' if x['nights'] != 1 else ''} cost {inr(x['saving_inr'])} more than that.")


def _trip_answer(f):
    trips = f["verdicts"]["trips"]
    if not trips:
        return "I cannot find that trip in the books."
    t = trips[0]
    if not t["saving_inr"]:
        return f"{t['trip_id']} ({t['date']}): {BEST_PHRASE}"
    lines = [f"Trip {t['trip_id']} could have cost less. It cost {inr(t['cost_inr'])} in all, and it could have "
             f"saved {inr(t['saving_inr'])}."]
    return "\n".join(lines + [_line(x) for x in f["savings"] if x["trip_id"] == t["trip_id"]])


def _answer(f):
    if f["focus"] == "trip":
        return _trip_answer(f)
    v, tr = f["verdicts"], f["travel"]
    out = [f"From {f['from']} to {f['to']}, DevX spent {inr(f['total_inr'])} in all."]
    if f["focus"] == "categories":
        out.append("The biggest costs: " + "; ".join(f"{c['label']} {inr(c['amount_inr'])} ({c['share_pct']}%)"
                                                     for c in f["categories"]) + ".")
    out.append(f"Travel was {inr(tr['total_inr'])}, which is {tr['share_pct']}% of all cost and "
               f"{tr['share_of_non_salary_pct']}% of cost without salaries. Flights were {inr(tr['flights_inr'])} "
               f"({tr['flights_share_pct']}%), trains {inr(tr['trains_inr'])} ({tr['trains_share_pct']}%), hotels "
               f"{inr(tr['hotels_inr'])} ({tr['hotels_share_pct']}%), and local and other travel {inr(tr['other_inr'])} "
               f"({tr['other_share_pct']}%).")
    if v["trip_count"]:
        out.append(f"Of {v['trip_count']} trips, {v['best_option_count']} were already the best option; "
                   f"{v['cheaper_option_count']} could have cost less, saving {inr(v['total_saving_inr'])}.")
    if f["savings"]:
        out += ["", "The biggest savings:"] + [_line(x) for x in f["savings"]]
        shown = {x["trip_id"] for x in f["savings"]}
        more = v["cheaper_option_count"] - len(shown)
        if more > 0:
            out.append(f"{more} more trip{'s' if more != 1 else ''} had smaller savings.")
    if f["suggestions"]:
        out += ["", "What to change:"]
        for n, s in enumerate(f["suggestions"], 1):
            out.append(f"{n}. {s['text']} This would have saved {inr(s['saving_inr'])} on {s['count']} {s['unit']}.")
    best = [t for t in v["trips"] if not t["saving_inr"]]
    if best:
        out.append("")
        if len(best) <= 5:
            out += [f"{t['trip_id']} ({t['date']}): {BEST_PHRASE}" for t in best]
        else:
            out.append(f"All other trips ({len(best)}): {BEST_PHRASE}")
    return "\n".join(out)


def brain(request):
    prompt = request.messages[0]["content"]
    facts = json.loads(prompt.rsplit(MARKER, 1)[1].strip().split("\n", 1)[0])
    return ModelReply(text=json.dumps({"answer": _answer(facts)}))
