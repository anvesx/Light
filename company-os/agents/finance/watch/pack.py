"""Finance watch agent pack: reads DevX's books and tells the finance lead about money that needs a look."""
import json
import re

from company_data.simulated_today import TODAY
from control_plane.connectors.tool_reply import days_before, days_between
from contract.types import ToolCall
from lifecycle_kit.action_tools import make_create_followup_task, make_send_private_message
from lifecycle_kit.agent_pack import AgentPack
from control_plane.connectors.books_tools import books_tools

AREA = "devx-internal"
DUPLICATE_DAYS = 10           # same vendor and amount within this many days
RECENT_DAYS = 14              # a duplicate or payment is news for this long after it happens
LARGE_PAYMENT_INR = 500_000   # "over 5 lakh"
NEW_VENDOR_DAYS = 30
TRAVEL_SHARE = 0.20
KINDS = ("duplicate_invoice", "large_payment_new_vendor", "budget_overrun", "travel_share_of_salary")
FOLLOWUP_KINDS = ("duplicate_invoice", "large_payment_new_vendor")
MARKER = "FINDINGS_JSON:"


def _read(ctx, name, args=None):
    """Run one read tool through the guard. Returns the parsed JSON, or {} if the read was refused."""
    result = ctx.notes["invoke_tool"](name, args or {})["result"]
    try:
        data = json.loads(result)
    except ValueError:
        return {}
    return data if isinstance(data, dict) and "error" not in data else {}


def _inr(amount):
    return f"INR {amount:,}"


def _duplicates(invoices, as_of):
    groups = {}
    for inv in invoices:
        groups.setdefault((inv["vendor_id"], inv["amount_inr"]), []).append(inv)
    found = []
    for group in groups.values():
        group.sort(key=lambda i: (i["date"], i["invoice_id"]))
        for a, b in zip(group, group[1:]):
            gap = days_between(b["date"], a["date"])
            if gap <= DUPLICATE_DAYS and days_between(as_of, b["date"]) < RECENT_DAYS:
                found.append({"kind": "duplicate_invoice", "ids": [a["invoice_id"], b["invoice_id"]],
                              "amount_inr": b["amount_inr"],
                              "facts": {"vendor": b["vendor"], "invoice_nos": [a["invoice_no"], b["invoice_no"]],
                                        "dates": [a["date"], b["date"]], "gap_days": gap,
                                        "statuses": [a["status"], b["status"]]}})
    return found


def _new_vendor_payments(payments):
    return [{"kind": "large_payment_new_vendor", "ids": [p["payment_id"], p["invoice_id"]],
             "amount_inr": p["amount_inr"],
             "facts": {"vendor": p["vendor"], "vendor_created_on": p["vendor_created_on"],
                       "vendor_age_days": p["vendor_age_days"], "payment_date": p["date"],
                       "approved_by": p["approved_by"]}}
            for p in payments if p["amount_inr"] > LARGE_PAYMENT_INR and p["vendor_age_days"] < NEW_VENDOR_DAYS]


def _overruns(rows):
    return [{"kind": "budget_overrun", "ids": [f"{r['team']}:{r['month']}:{r['category']}"],
             "amount_inr": r["spend_inr"],
             "facts": {"team": r["team"], "month": r["month"], "category": r["category"],
                       "budget_inr": r["budget_inr"], "over_by_inr": r["spend_inr"] - r["budget_inr"]}}
            for r in rows if r["over_budget"]]


def _travel(rows):
    return [{"kind": "travel_share_of_salary", "ids": [f"{r['team']}:{r['month']}"],
             "amount_inr": r["travel_spend_inr"],
             "facts": {"team": r["team"], "month": r["month"], "headcount": r["headcount"],
                       "team_salary_total_inr": r["team_salary_total_inr"],
                       "share_percent": round(r["travel_share_of_salary"] * 100, 1)}}
            for r in rows if r["travel_share_of_salary"] is not None and r["travel_share_of_salary"] > TRAVEL_SHARE]


def _key(finding):
    return (finding["kind"], tuple(sorted(finding["ids"])), finding["amount_inr"])


class FinanceWatchPack(AgentPack):
    name = "finance_watch"
    starter_roles = frozenset({"finance_lead", "ceo", "system"})
    approver_roles = frozenset({"finance_lead", "ceo"})

    def __init__(self, parts):
        self.parts = parts
        self.directory = parts.directory

    def tools(self):
        return [*books_tools(self.parts.data_conn), make_send_private_message(self.parts.outbox),
                make_create_followup_task(self.parts.memory)]

    def system_prompt(self):
        return ("You are the finance watch agent for DevX. Explain each finding for the finance lead in plain, short "
                "sentences: the evidence, why it matters, and one next step. Use only the facts you are given. Never "
                "state one person's salary: team totals only. Answer with JSON only.")

    def record(self, ctx):
        return {"invoices": _read(ctx, "invoices_window", {"days": 30}),
                "payments": _read(ctx, "payments_window", {"days": RECENT_DAYS, "min_amount_inr": LARGE_PAYMENT_INR + 1}),
                "budget": _read(ctx, "budget_vs_spend"), "travel": _read(ctx, "travel_share_of_salary")}

    def understand(self, ctx, recorded):
        as_of = (recorded["invoices"].get("as_of") or ctx.task.inputs.get("as_of") or TODAY)
        findings = (_duplicates(recorded["invoices"].get("invoices", []), as_of)
                    + _new_vendor_payments(recorded["payments"].get("payments", []))
                    + _overruns(recorded["budget"].get("rows", []))
                    + _travel(recorded["travel"].get("rows", [])))
        ctx.notes["as_of"] = as_of
        if not findings:
            return {"quiet": True, "as_of": as_of}
        return {"as_of": as_of, "findings": findings}

    def decision_prompt(self, understood):
        return (f"Today is {understood['as_of']}. These findings were computed from DevX's books.\n"
                f"{MARKER}\n{json.dumps(understood['findings'], sort_keys=True)}\n"
                'Reply with final JSON only: {"findings": [{"kind", "ids", "amount_inr", "evidence", '
                '"why_it_matters", "next_step"}], "followups": [{"title", "ids"}]}. Copy kind, ids and amount_inr '
                "exactly. A followup is only for a duplicate_invoice or large_payment_new_vendor finding.")

    def parse_decision(self, final_text):
        text = final_text.strip()
        start, end = text.find("{"), text.rfind("}")
        data = json.loads(text[start:end + 1])
        return {"findings": list(data.get("findings", [])), "followups": list(data.get("followups", []))}

    def check(self, ctx, decision, understood):
        known = {_key(f): f for f in understood["findings"]}
        known_ids = {i for f in understood["findings"] for i in f["ids"]}
        problems = []
        for f in decision["findings"]:
            try:
                key = _key(f)
            except (KeyError, TypeError):
                problems.append(f"finding is missing kind, ids or amount_inr: {f!r:.80}")
                continue
            if key not in known:
                problems.append(f"finding {f.get('kind')} {f.get('ids')} amount {f.get('amount_inr')} "
                                "does not match the computed findings")
            for field in ("evidence", "why_it_matters", "next_step"):
                if not str(f.get(field, "")).strip():
                    problems.append(f"finding {f.get('ids')} has no {field}")
        for fu in decision["followups"]:
            ids = fu.get("ids") or []
            kinds = {known[k]["kind"] for k in known if set(ids) & set(known[k]["ids"])}
            if not ids or not set(ids) <= known_ids or not kinds <= set(FOLLOWUP_KINDS) or not kinds:
                problems.append(f"follow-up {fu.get('title')!r} does not point at a duplicate or new-vendor finding")
            if not str(fu.get("title", "")).strip():
                problems.append("a follow-up has no title")
        problems += self._salary_problems(decision, understood)
        return problems

    def _salary_problems(self, decision, understood):
        """Stop any text that shows one person's monthly salary. Team totals are allowed."""
        allowed = {str(f["amount_inr"]) for f in understood["findings"]}
        allowed |= {str(f["facts"].get("team_salary_total_inr")) for f in understood["findings"]}
        salaries = {str(r[0]) for r in self.parts.data_conn.execute(
            "SELECT monthly_salary_inr FROM people WHERE monthly_salary_inr IS NOT NULL")}
        text = json.dumps(decision)
        shown = {n.replace(",", "") for n in re.findall(r"\d[\d,]*\d|\d", text)}
        leaked = sorted((shown & salaries) - allowed)
        return [f"text shows an amount that matches one person's salary ({n}); team totals only" for n in leaked]

    def act(self, ctx, decision):
        lead = self.directory.people_by_role("finance_lead")
        ceo = self.directory.people_by_role("ceo")
        calls = []
        if decision["findings"]:
            text = _message(decision["findings"], ctx.notes.get("as_of", TODAY))
            calls += [ToolCall(f"act-{p}", "send_private_message",
                               {"to_person_id": p, "text": text, "kind": "finance_flag"}) for p in lead]
            travel = [f for f in decision["findings"] if f["kind"] == "travel_share_of_salary"]
            if travel:
                text = _message(travel, ctx.notes.get("as_of", TODAY))
                calls += [ToolCall(f"act-{p}-travel", "send_private_message",
                                   {"to_person_id": p, "text": text, "kind": "finance_flag"}) for p in ceo]
        for fu in decision["followups"]:
            owner = lead[0] if lead else None
            calls.append(ToolCall(f"act-followup-{len(calls)}", "create_followup_task",
                                  {"area_id": AREA, "title": fu["title"], "owner_id": owner}))
        return calls

    def remember(self, ctx, decision, acted):
        severity = {"duplicate_invoice": "medium", "large_payment_new_vendor": "high",
                    "budget_overrun": "low", "travel_share_of_salary": "medium"}
        case_ids = [self.parts.memory.add_case(ctx.run_id, self.name, AREA, f"{f['kind']}: {', '.join(f['ids'])}",
                                               severity[f["kind"]], f)
                    for f in decision["findings"]]
        return {"cases": case_ids}


def _message(findings, as_of):
    lines = [f"Finance watch, {as_of}: {len(findings)} item(s) need a look."]
    for n, f in enumerate(findings, 1):
        lines += [f"{n}. {f['kind'].replace('_', ' ')} ({', '.join(f['ids'])}, {_inr(f['amount_inr'])})",
                  f"   Evidence: {f['evidence']}", f"   Why it matters: {f['why_it_matters']}",
                  f"   Next step: {f['next_step']}"]
    return "\n".join(lines)


def make_pack(parts):
    return FinanceWatchPack(parts)
