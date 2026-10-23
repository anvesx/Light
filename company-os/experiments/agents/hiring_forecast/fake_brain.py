"""Deterministic stand-in for the model: reads the forecast JSON and writes a plain-English hiring note."""
import json

from contract.types import ModelReply

MARK = "FORECAST_JSON:\n"


def brain(request):
    content = request.messages[-1]["content"]
    data = json.loads(content[content.index(MARK) + len(MARK):])
    short, spare = [], []
    for t in data["teams"]:
        if t["status"] == "short":
            short.append({"team": t["team"], "shortfall_hours_per_week": t["shortfall_hours_per_week"],
                          "starts_week": t["starts_week"], "hire_by": t["hire_by"], "why": _why_short(t)})
        elif t["status"] == "spare":
            spare.append({"team": t["team"], "spare_hours_per_week": t["spare_hours_per_week"], "why": _why_spare(t)})
    return ModelReply(text=json.dumps({"short_teams": short, "spare_teams": spare,
                                       "assumptions": data["assumptions"], "summary": _summary(data, short, spare)}))


def _why_short(t):
    people = "person" if t["people_needed"] == 1 else "people"
    when = "Hiring should start now, because the shortfall is close." if t["start_hiring_now"] else \
        "Hiring takes time, so the search should begin on that date."
    return (f"The {t['team']} team has {t['people']} people and about {t['usable_hours_per_week']} usable hours a week. "
            f"From the week of {t['starts_week']} the work coming is more than that, by up to "
            f"{t['shortfall_hours_per_week']} hours a week. That is about {t['people_needed']} more {people}. {when}")


def _why_spare(t):
    return (f"The {t['team']} team has about {t['usable_hours_per_week']} usable hours a week and the work coming "
            f"leaves about {t['spare_hours_per_week']} hours a week free. HR can hire fewer people here, or none.")


def _summary(data, short, spare):
    first = data["week_starts"][0]
    if short:
        names = ", ".join(s["team"] for s in short)
        head = f"Short of people in the next {len(data['week_starts'])} weeks from {first}: {names}."
    else:
        head = f"No team is short of people in the next {len(data['week_starts'])} weeks from {first}."
    tail = f" Spare hours: {', '.join(s['team'] for s in spare)}." if spare else ""
    return head + tail
