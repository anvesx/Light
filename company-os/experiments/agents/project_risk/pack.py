"""Project risk agent pack: finds trouble early on a client's projects and tells the project's CSM privately."""
import json
import re
from datetime import date, timedelta

from connectors.project_tools import project_tools
from connectors.slack_tools import make_client_channel_activity
from contract.types import ToolCall
from lifecycle_kit.action_tools import make_create_followup_task, make_send_private_message
from lifecycle_kit.agent_pack import AgentPack

OVER_SOW_PCT, OPEN_SHARE, SILENT_DAYS, OVERDUE_COUNT = 115, 0.30, 14, 5
OVERLOAD_HOURS, OVERLOAD_WEEKS = 55, 3
THRESHOLDS = {"over_sow_pct": OVER_SOW_PCT, "open_task_share_pct": int(OPEN_SHARE * 100), "silent_days": SILENT_DAYS,
              "overdue_tasks": OVERDUE_COUNT, "overload_hours_per_week": OVERLOAD_HOURS,
              "overload_weeks": OVERLOAD_WEEKS}
SEVERITIES = ("low", "medium", "high")
PROMPT_MARK = "SIGNALS_JSON:\n"
ID_RE = re.compile(r"\b(?:PR|SW|SC|CASE|[PXSC])\d{1,3}(?:-\d+)?\b")
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
NUM_RE = re.compile(r"\d+(?:\.\d+)?")
SYSTEM = ("You help a CSM (a DevX project manager) spot project trouble early. Use only the numbers and ids in the "
          "signals you are given. Write short, plain, non-technical English. Never build a people or bandwidth report.")


class ProjectRiskPack(AgentPack):
    name = "project_risk"
    starter_roles = frozenset({"csm", "project_lead", "ceo", "rnd_lead", "system"})
    approver_roles = frozenset({"csm", "ceo"})

    def __init__(self, parts):
        self.parts = parts

    def tools(self):
        p = self.parts
        return [*project_tools(p.data_conn), make_client_channel_activity(p.data_conn),
                make_send_private_message(p.outbox), make_create_followup_task(p.memory)]

    def system_prompt(self):
        return SYSTEM

    # record: reads only through the checked tool path
    def record(self, ctx):
        read = lambda name, args=None: _read(ctx, name, args or {})
        overview = read("project_overview")
        rec = {"overview": overview, "activity": read("client_channel_activity"), "hours": {}, "overdue": {}}
        for p in overview["projects"]:
            if p["status"] == "active":
                rec["hours"][p["project_id"]] = read("weekly_hours_by_person",
                                                     {"weeks": 4, "project_id": p["project_id"]})["rows"]
            if p["status"] == "active" and p["tasks_overdue"] >= OVERDUE_COUNT:
                rec["overdue"][p["project_id"]] = read(
                    "project_tasks", {"project_id": p["project_id"], "state": "overdue", "limit": 200})
        return rec

    # understand: every signal is computed here, with fixed thresholds
    def understand(self, ctx, rec):
        as_of = rec["overview"]["as_of"]
        silent = {r["project_id"]: r for r in rec["activity"]["projects"]}
        signals = []
        for p in rec["overview"]["projects"]:
            if p["status"] != "active":
                continue
            base = {"project_id": p["project_id"], "project_name": p["name"], "csm_id": p["csm_id"],
                    "lead_id": p["lead_id"]}
            signals += _project_signals(base, p, silent.get(p["project_id"]), rec["overdue"].get(p["project_id"]))
        signals += _overload_signals(rec, as_of)
        if not signals:
            return {"quiet": True}
        return {"as_of": as_of, "client_id": ctx.task.area_id, "thresholds": THRESHOLDS, "signals": signals}

    def decision_prompt(self, understood):
        return ("Below are the risk signals found today for one client. For each signal write a flag: the evidence in "
                "numbers, why it matters, and a suggested next step. For high-severity flags you may propose a follow-up "
                "task. Reply with final JSON only: "
                '{"flags": [{"signal", "project_id", "person_id" (only for overload), "severity" (low|medium|high), '
                '"evidence", "why_it_matters", "next_step"}], "followups": [{"title", "owner_id"}]}.\n'
                + PROMPT_MARK + json.dumps(understood, indent=1))

    def parse_decision(self, final_text):
        text = final_text.strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
        data = json.loads(text)
        if not isinstance(data.get("flags"), list):
            raise ValueError("no flags list")
        data.setdefault("followups", [])
        return data

    # check: nothing reaches a person unless it matches the code's findings
    def check(self, ctx, decision, understood):
        problems = []
        by_key = {(s["signal"], s["project_id"], s.get("person_id")): s for s in understood["signals"]}
        known_ids = set(ID_RE.findall(json.dumps(understood)))
        known_dates = set(DATE_RE.findall(json.dumps(understood)))
        known_nums = {float(n) for n in NUM_RE.findall(DATE_RE.sub("", ID_RE.sub("", json.dumps(understood))))}
        for i, f in enumerate(decision["flags"]):
            tag = f"flag {i + 1}"
            sig = by_key.get((f.get("signal"), f.get("project_id"), f.get("person_id")))
            if sig is None:
                problems.append(f"{tag}: no matching signal for {f.get('signal')}/{f.get('project_id')}/{f.get('person_id')}")
                continue
            if f.get("severity") not in SEVERITIES:
                problems.append(f"{tag}: bad severity {f.get('severity')!r}")
            for key in ("evidence", "why_it_matters", "next_step"):
                if not isinstance(f.get(key), str) or not f[key].strip():
                    problems.append(f"{tag}: missing {key}")
                else:
                    problems += _check_text(f"{tag} {key}", f[key], known_ids, known_dates, known_nums)
            problems += self._check_recipient(tag, sig)
        high = any(f.get("severity") == "high" for f in decision["flags"])
        owners = {s["csm_id"] for s in understood["signals"]} | {s["lead_id"] for s in understood["signals"]}
        if decision["followups"] and not high:
            problems.append("follow-up proposed but no flag is high severity")
        for j, fu in enumerate(decision["followups"]):
            if fu.get("owner_id") not in owners:
                problems.append(f"follow-up {j + 1}: owner {fu.get('owner_id')!r} is not the project's CSM or lead")
            problems += _check_text(f"follow-up {j + 1}", str(fu.get("title", "")), known_ids, known_dates, known_nums)
        ctx.notes["risk_signals"] = by_key
        return problems

    def _check_recipient(self, tag, sig):
        d = self.parts.directory
        if not (d.is_devx(sig["csm_id"]) and d.role(sig["csm_id"]) == "csm"):
            return [f"{tag}: recipient {sig['csm_id']!r} is not a DevX CSM"]
        return []

    # act: one private message per CSM; follow-ups wait for approval
    def act(self, ctx, decision):
        by_key = ctx.notes["risk_signals"]
        per_csm = {}
        for f in decision["flags"]:
            sig = by_key[(f["signal"], f["project_id"], f.get("person_id"))]
            per_csm.setdefault(sig["csm_id"], []).append((f, sig))
        calls = [ToolCall(f"msg-{csm}", "send_private_message",
                          {"to_person_id": csm, "text": _message(items, self.parts.directory), "kind": "flag"})
                 for csm, items in sorted(per_csm.items())]
        for n, fu in enumerate(decision["followups"]):
            calls.append(ToolCall(f"fu-{n}", "create_followup_task",
                                  {"area_id": ctx.task.area_id, "title": fu["title"], "owner_id": fu["owner_id"]}))
        return calls

    def remember(self, ctx, decision, acted):
        by_key = ctx.notes["risk_signals"]
        cases = []
        for f in decision["flags"]:
            sig = by_key[(f["signal"], f["project_id"], f.get("person_id"))]
            subject = f"{f['signal']}:{f.get('person_id') or f['project_id']}"
            evidence = {"project_id": f["project_id"], "person_id": f.get("person_id"), "text": f["evidence"],
                        "why_it_matters": f["why_it_matters"], "next_step": f["next_step"], "facts": sig["facts"]}
            cases.append(self.parts.memory.add_case(ctx.run_id, self.name, ctx.task.area_id, subject,
                                                    f["severity"], evidence))
        return {"cases": cases, "flags": len(decision["flags"]), "followups_proposed": len(decision["followups"]),
                "held": list(ctx.held)}


def make_pack(parts) -> ProjectRiskPack:
    return ProjectRiskPack(parts)


def _read(ctx, name, args):
    out = ctx.notes["invoke_tool"](name, args)
    if out["verdict"] != "allow":
        raise RuntimeError(f"read {name} not allowed: {out['result']}")
    data = json.loads(out["result"])
    if "error" in data:
        raise RuntimeError(f"read {name} failed: {data['error']}")
    return data


def _project_signals(base, p, activity, overdue):
    out = []
    pct, share = p["logged_pct_of_estimate"], p["open_task_share"]
    if pct is not None and pct > OVER_SOW_PCT and share is not None and share >= OPEN_SHARE:
        est = p["estimate_hours_with_changes"]
        out.append({**base, "signal": "hours_over_sow", "severity_hint": "high" if pct >= 130 else "medium",
                    "facts": {"hours_logged": p["hours_logged"], "estimate_hours": est, "logged_pct": pct,
                              "hours_over_estimate": round(p["hours_logged"] - est, 1),
                              "tasks_open": p["tasks_open"], "tasks_total": p["tasks_total"],
                              "open_task_pct": round(100 * share)}})
    if activity and activity["days_silent"] >= SILENT_DAYS:
        d = activity["days_silent"]
        out.append({**base, "signal": "client_silent", "severity_hint": "high" if d >= 28 else "medium",
                    "facts": {"days_silent": d, "last_client_message_on": activity["last_client_message_on"]}})
    if p["tasks_overdue"] >= OVERDUE_COUNT:
        tasks = (overdue or {}).get("tasks", [])
        oldest = min((t["due_on"] for t in tasks), default=None)
        facts = {"overdue_tasks": p["tasks_overdue"], "tasks_open": p["tasks_open"], "tasks_total": p["tasks_total"]}
        if oldest:
            facts["oldest_due_on"] = oldest
        out.append({**base, "signal": "overdue_tasks", "severity_hint": "high" if p["tasks_overdue"] >= 8 else "medium",
                    "facts": facts})
    unacc, est = p["unaccepted_change_hours"], p["estimate_hours_with_changes"]
    if est is not None and unacc > 0 and unacc > max(est - p["hours_logged"], 0):
        left = round(max(est - p["hours_logged"], 0), 1)
        out.append({**base, "signal": "sow_change_exceeds_remaining", "severity_hint": "low",
                    "facts": {"unaccepted_change_hours": unacc, "hours_left": left, "estimate_hours": est,
                              "hours_logged": p["hours_logged"]}})
    return out


def _overload_signals(rec, as_of):
    d = date.fromisoformat(as_of)
    last_sunday = d - timedelta(days=(d.weekday() + 1) % 7)
    mondays = [(last_sunday - timedelta(days=6 + 7 * k)).isoformat() for k in range(OVERLOAD_WEEKS)][::-1]
    totals, by_project = {}, {}
    for pid, rows in rec["hours"].items():
        for r in rows:
            totals[(r["person_id"], r["week_start"])] = totals.get((r["person_id"], r["week_start"]), 0) + r["hours"]
            if r["week_start"] in mondays:
                by_project[(r["person_id"], pid)] = by_project.get((r["person_id"], pid), 0) + r["hours"]
    projects = {p["project_id"]: p for p in rec["overview"]["projects"]}
    out = []
    for person in sorted({k[0] for k in totals}):
        weeks = [round(totals.get((person, m), 0), 1) for m in mondays]
        if not all(h > OVERLOAD_HOURS for h in weeks):
            continue
        pid = max((k for k in by_project if k[0] == person), key=lambda k: (by_project[k], k[1]))[1]
        p = projects[pid]
        out.append({"project_id": pid, "project_name": p["name"], "csm_id": p["csm_id"], "lead_id": p["lead_id"],
                    "person_id": person, "signal": "overloaded_engineer",
                    "severity_hint": "high" if min(weeks) >= 60 else "medium",
                    "facts": {"weeks_in_a_row": OVERLOAD_WEEKS, "weekly_hours": weeks, "lowest_week_hours": min(weeks),
                              "first_week_start": mondays[0], "last_week_end": last_sunday.isoformat()}})
    return out


def _check_text(tag, text, known_ids, known_dates, known_nums):
    problems = []
    for i in set(ID_RE.findall(text)) - known_ids:
        problems.append(f"{tag}: id {i} is not in the signals")
    for dt in set(DATE_RE.findall(text)) - known_dates:
        problems.append(f"{tag}: date {dt} is not in the signals")
    for n in set(NUM_RE.findall(DATE_RE.sub("", ID_RE.sub("", text)))):
        if float(n) not in known_nums:
            problems.append(f"{tag}: number {n} is not in the signals")
    return problems


def _message(items, directory):
    lines = ["Project risk flags for your projects:"]
    for f, sig in items:
        person = directory.get(f["person_id"]) if f.get("person_id") else None
        who = f" ({person['name']})" if person else ""
        lines.append(f"\n[{f['severity'].upper()}] {sig['project_name']} ({f['project_id']}){who}\n"
                     f"What we see: {f['evidence']}\nWhy it matters: {f['why_it_matters']}\n"
                     f"Suggested next step: {f['next_step']}")
    return "\n".join(lines)
