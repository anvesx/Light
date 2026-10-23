"""Hiring forecast agent pack: tells HR and the CEO which team runs short of people in the next weeks, and when to start hiring."""
import json
import math
import re
from datetime import date, timedelta

from connectors.staffing_tools import make_pipeline_demand, make_remaining_sow_hours, make_team_capacity_and_load
from contract.types import ToolCall
from lifecycle_kit.action_tools import make_send_private_message
from lifecycle_kit.agent_pack import AgentPack

AREA = "devx-internal"
WEEK_HOURS, UTILISATION = 40, 0.8          # usable hours per person per week = 40 x 0.8
HIRING_LEAD_WEEKS, HORIZON_WEEKS = 4, 8
PROPOSAL_WEIGHT, BUILD_WEEKS = 0.5, 12     # a proposal counts for half; new work is spread over 12 weeks
SPARE_PCT = 15                              # spare = at least 15% of usable hours free on average
ASSUMPTIONS = [
    f"A person has {WEEK_HOURS} hours a week and we plan on {round(UTILISATION * 100)}% of that (utilisation {UTILISATION}).",
    "Work already signed: the hours left on each active project are spread evenly from today to its planned end date.",
    "Those hours are split between teams in the same share as the open task estimates of the project.",
    "New work: a won deal that has not started counts in full, a proposal counts for "
    f"{round(PROPOSAL_WEIGHT * 100)}%. Deal value becomes hours at the average signed rate, and the work is spread over "
    f"{BUILD_WEEKS} weeks from the expected start.",
    "New work is split between teams in the same share as the signed work.",
    f"Hiring takes about {HIRING_LEAD_WEEKS} weeks, so the hiring start is {HIRING_LEAD_WEEKS} weeks before the short week.",
    f"We look {HORIZON_WEEKS} weeks ahead. A team has spare hours when at least {SPARE_PCT}% of its usable hours are free on average.",
]
PROMPT_MARK = "FORECAST_JSON:\n"
PERSON_ID_RE = re.compile(r"\bP\d{2,3}\b")
SALARY_RE = re.compile(r"salar|\bctc\b|\bwage|\bpay ?roll|\bpay\b", re.I)
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
NUM_RE = re.compile(r"\d+(?:\.\d+)?")
SYSTEM = ("You help HR and the CEO plan hiring. Use only the numbers and dates in the forecast you are given. "
          "Write short, plain English that an HR person reads quickly. Talk about teams only, never about one person "
          "and never about pay.")


class HiringForecastPack(AgentPack):
    name = "hiring_forecast"
    starter_roles = frozenset({"hr", "ceo", "system"})
    approver_roles = frozenset({"hr", "ceo"})

    def __init__(self, parts):
        self.parts = parts

    def tools(self):
        p = self.parts
        return [make_team_capacity_and_load(p.data_conn), make_pipeline_demand(p.data_conn),
                make_remaining_sow_hours(p.data_conn), make_send_private_message(p.outbox)]

    def system_prompt(self):
        return SYSTEM

    # record: reads only through the checked tool path
    def record(self, ctx):
        read = lambda name, args=None: _read(ctx, name, args or {})
        return {"capacity": read("team_capacity_and_load", {"weeks": 4}), "pipeline": read("pipeline_demand"),
                "sow": read("remaining_sow_hours")}

    def understand(self, ctx, rec):
        forecast = build_forecast(rec["capacity"], rec["pipeline"], rec["sow"])
        if not any(t["status"] in ("short", "spare") for t in forecast["teams"]):
            return {"quiet": True}
        ctx.notes["forecast"] = forecast
        return forecast

    def decision_prompt(self, understood):
        return ("Below is this week's hiring forecast, worked out by code. Explain it for HR. For each short team give "
                "why it is short and when to start hiring. For each team with spare hours say why HR should hire less "
                "there. List the assumptions. Reply with final JSON only: "
                '{"short_teams": [{"team", "shortfall_hours_per_week", "starts_week", "hire_by", "why"}], '
                '"spare_teams": [{"team", "spare_hours_per_week", "why"}], "assumptions": [text], "summary": text}.\n'
                + PROMPT_MARK + json.dumps(understood, indent=1))

    def parse_decision(self, final_text):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", final_text.strip())
        data = json.loads(text)
        for key in ("short_teams", "spare_teams", "assumptions"):
            if not isinstance(data.get(key), list):
                raise ValueError(f"no {key} list")
        return data

    # check: numbers must match the code's forecast; no person ids or pay in the text
    def check(self, ctx, decision, understood):
        problems = []
        teams = {t["team"]: t for t in understood["teams"]}
        known_dates = set(DATE_RE.findall(json.dumps(understood)))
        known_nums = {float(n) for n in NUM_RE.findall(DATE_RE.sub("", json.dumps(understood)))}
        want_short = {t for t, v in teams.items() if v["status"] == "short"}
        want_spare = {t for t, v in teams.items() if v["status"] == "spare"}
        got_short = [s.get("team") for s in decision["short_teams"]]
        got_spare = [s.get("team") for s in decision["spare_teams"]]
        if set(got_short) != want_short or len(got_short) != len(set(got_short)):
            problems.append(f"short teams {sorted(map(str, got_short))} do not match the forecast {sorted(want_short)}")
        if set(got_spare) != want_spare or len(got_spare) != len(set(got_spare)):
            problems.append(f"spare teams {sorted(map(str, got_spare))} do not match the forecast {sorted(want_spare)}")
        for s in decision["short_teams"]:
            t = teams.get(s.get("team"))
            if t and t["status"] == "short":
                for key, want in (("shortfall_hours_per_week", t["shortfall_hours_per_week"]),
                                  ("starts_week", t["starts_week"]), ("hire_by", t["hire_by"])):
                    if s.get(key) != want:
                        problems.append(f"{s['team']}: {key} is {s.get(key)!r}, the forecast says {want!r}")
                problems += _check_text(f"{s['team']} why", s.get("why"), known_dates, known_nums)
        for s in decision["spare_teams"]:
            t = teams.get(s.get("team"))
            if t and t["status"] == "spare":
                if s.get("spare_hours_per_week") != t["spare_hours_per_week"]:
                    problems.append(f"{s['team']}: spare_hours_per_week is {s.get('spare_hours_per_week')!r}, "
                                    f"the forecast says {t['spare_hours_per_week']!r}")
                problems += _check_text(f"{s['team']} why", s.get("why"), known_dates, known_nums)
        if not decision["assumptions"]:
            problems.append("no assumptions stated")
        for i, a in enumerate(decision["assumptions"]):
            problems += _check_text(f"assumption {i + 1}", a, known_dates, known_nums)
        problems += _check_text("summary", decision.get("summary"), known_dates, known_nums)
        return problems

    # act: the same note to every HR person and the CEO
    def act(self, ctx, decision):
        d = self.parts.directory
        text = _message(decision, ctx.notes["forecast"]["as_of"])
        recipients = d.people_by_role("hr") + d.people_by_role("ceo")
        return [ToolCall(f"msg-{pid}", "send_private_message", {"to_person_id": pid, "text": text, "kind": "forecast"})
                for pid in recipients]

    def remember(self, ctx, decision, acted):
        forecast = ctx.notes["forecast"]
        teams, as_of, cases = {t["team"]: t for t in forecast["teams"]}, forecast["as_of"], []
        for s in decision["short_teams"]:
            severity = "high" if teams.get(s["team"], {}).get("start_hiring_now") else "medium"
            cases.append(self.parts.memory.add_case(ctx.run_id, self.name, ctx.task.area_id, f"short:{s['team']}",
                                                    severity, {**s, "as_of": as_of}))
        for s in decision["spare_teams"]:
            cases.append(self.parts.memory.add_case(ctx.run_id, self.name, ctx.task.area_id, f"spare:{s['team']}",
                                                    "low", {**s, "as_of": as_of}))
        return {"cases": cases, "short": len(decision["short_teams"]), "spare": len(decision["spare_teams"])}


def make_pack(parts) -> HiringForecastPack:
    return HiringForecastPack(parts)


def _read(ctx, name, args):
    out = ctx.notes["invoke_tool"](name, args)
    if out["verdict"] != "allow":
        raise RuntimeError(f"read {name} not allowed: {out['result']}")
    data = json.loads(out["result"])
    if "error" in data:
        raise RuntimeError(f"read {name} failed: {data['error']}")
    return data


def _monday_on_or_after(day):
    return day + timedelta(days=(7 - day.weekday()) % 7)


def build_forecast(capacity, pipeline, sow) -> dict:
    """The whole forecast, in code: weekly demand against usable capacity for each team."""
    as_of = date.fromisoformat(capacity["as_of"])
    weeks = [_monday_on_or_after(as_of) + timedelta(weeks=k) for k in range(HORIZON_WEEKS)]
    teams = {t["team"]: t for t in capacity["teams"]}
    demand = {name: [0.0] * HORIZON_WEEKS for name in teams}
    signed_by_team = {name: 0.0 for name in teams}
    for p in sow["projects"]:
        if p["status"] != "active":
            continue
        open_by_team = {k: v for k, v in p["open_task_estimate_by_team"].items() if k in teams}
        total_open = sum(open_by_team.values())
        if p["remaining_hours"] <= 0 or total_open <= 0:
            continue
        end = max(date.fromisoformat(p["planned_end_on"]), as_of + timedelta(days=7))
        weeks_left = math.ceil((end - as_of).days / 7)
        for name, h in open_by_team.items():
            share = p["remaining_hours"] * h / total_open
            signed_by_team[name] += share
            for k, w in enumerate(weeks):
                if w <= end:
                    demand[name][k] += share / weeks_left
    new_hours, deals = 0.0, 0
    signed_total = sum(signed_by_team.values())
    for lead in pipeline["leads"]:
        if lead["started"] or lead["stage"] not in ("won", "proposal") or signed_total <= 0:
            continue
        hours = lead["approx_hours"] * (1.0 if lead["stage"] == "won" else PROPOSAL_WEIGHT)
        first = date.fromisoformat(lead["expected_start"])
        first -= timedelta(days=first.weekday())
        new_hours, deals = new_hours + hours, deals + 1
        for name in teams:
            for k, w in enumerate(weeks):
                if first <= w < first + timedelta(weeks=BUILD_WEEKS):
                    demand[name][k] += hours * signed_by_team[name] / signed_total / BUILD_WEEKS
    usable_per_person = WEEK_HOURS * UTILISATION
    out = []
    for name in sorted(teams):
        t = teams[name]
        usable = round(t["people"] * usable_per_person, 1)
        weekly = [round(x, 1) for x in demand[name]]
        gaps = [round(h - usable, 1) for h in weekly]
        done = [w["hours"] for w in t["weeks"] if w["week_complete"]]
        row = {"team": name, "people": t["people"], "usable_hours_per_week": usable, "demand_hours_by_week": weekly,
               "recent_logged_hours_per_week": round(sum(done) / len(done), 1) if done else None, "status": "balanced"}
        if max(gaps) > 0:
            k = next(i for i, g in enumerate(gaps) if g > 0)
            start, peak = weeks[k], max(gaps)
            hire_by = start - timedelta(weeks=HIRING_LEAD_WEEKS)
            row.update(status="short", shortfall_hours_per_week=peak, first_week_shortfall_hours=gaps[k],
                       starts_week=start.isoformat(), hire_by=hire_by.isoformat(),
                       start_hiring_now=hire_by <= as_of, people_needed=math.ceil(peak / usable_per_person))
        else:
            spare = round(sum(usable - h for h in weekly) / HORIZON_WEEKS, 1)
            if spare >= usable * SPARE_PCT / 100:
                row.update(status="spare", spare_hours_per_week=spare, spare_people=int(spare // usable_per_person))
        out.append(row)
    return {"as_of": as_of.isoformat(), "week_starts": [w.isoformat() for w in weeks], "teams": out,
            "new_work": {"deals_counted": deals, "weighted_hours": round(new_hours)}, "assumptions": ASSUMPTIONS}


def _check_text(tag, text, known_dates, known_nums):
    if not isinstance(text, str) or not text.strip():
        return [f"{tag}: missing text"]
    problems = []
    if PERSON_ID_RE.search(text):
        problems.append(f"{tag}: names a person id")
    if SALARY_RE.search(text):
        problems.append(f"{tag}: talks about pay")
    for dt in set(DATE_RE.findall(text)) - known_dates:
        problems.append(f"{tag}: date {dt} is not in the forecast")
    for n in set(NUM_RE.findall(DATE_RE.sub("", text))):
        if float(n) not in known_nums:
            problems.append(f"{tag}: number {n} is not in the forecast")
    return problems


def _message(decision, as_of):
    lines = ["Weekly hiring forecast (team level only):", "", decision["summary"].strip()]
    for s in decision["short_teams"]:
        when = (f"Start hiring now (the plan date {s['hire_by']} has passed)." if s["hire_by"] <= as_of
                else f"Start hiring by {s['hire_by']}.")
        lines.append(f"\n[SHORT] {s['team']}: about {s['shortfall_hours_per_week']} hours a week short, starting the week of "
                     f"{s['starts_week']}. {when}\n{s['why']}")
    for s in decision["spare_teams"]:
        lines.append(f"\n[SPARE] {s['team']}: about {s['spare_hours_per_week']} hours a week spare.\n{s['why']}")
    lines.append("\nAssumptions:")
    lines += [f"- {a}" for a in decision["assumptions"]]
    return "\n".join(lines)
