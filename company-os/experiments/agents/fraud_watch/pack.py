"""Store watch agent: finds unusual refund, discount and remake patterns and tells the retail client's CSM."""
import json
import re

from contract.types import ToolCall
from lifecycle_kit.action_tools import make_create_followup_task, make_send_private_message
from lifecycle_kit.agent_pack import AgentPack

from connectors.store_pos_tools import store_pos_tools

from .pattern_rules import BANNED, WINDOW_DAYS, find_patterns

NUMBER = re.compile(r"\d+(?:\.\d+)?")
PERSON_OR_STORE = re.compile(r"\b(?:S|ST)\d+\b")
MARKER = "PATTERNS_JSON:"
READS = ("refunds_by_staff", "discounts_by_staff", "remakes_by_staff")


def make_pack(parts, as_of=None):
    return FraudWatchPack(parts, as_of)


class FraudWatchPack(AgentPack):
    name = "fraud_watch"
    starter_roles = frozenset({"csm", "ceo", "system"})
    approver_roles = frozenset({"csm", "ceo"})

    def __init__(self, parts, as_of=None):
        self.parts, self.as_of = parts, as_of

    def tools(self):
        reads = [t for t in store_pos_tools(self.parts.data_conn) if t.name in READS]
        return reads + [make_send_private_message(self.parts.outbox), make_create_followup_task(self.parts.memory)]

    def system_prompt(self):
        return ("You help a DevX customer success manager review store activity. You only describe unusual patterns "
                "and show the evidence. You never accuse anyone and never say or suggest what a person intended.")

    def read_args(self):
        args = {"days": WINDOW_DAYS, "limit": 60}
        if self.as_of:
            args["as_of"] = self.as_of
        return args

    def record(self, ctx):
        invoke, out, problems = ctx.notes["invoke_tool"], {}, []
        for name in READS:
            entry = invoke(name, self.read_args())
            try:
                data = json.loads(entry["result"]) if entry["verdict"] == "allow" else None
            except ValueError:
                data = None
            if not isinstance(data, dict) or "error" in data:
                problems.append(f"{name}: {entry['result'][:120]}")
                data = {}
            out[name] = data
        return {"data": out, "problems": problems}

    def understand(self, ctx, recorded):
        if recorded["problems"]:
            return {"quiet": True, "read_problems": recorded["problems"]}
        d = recorded["data"]
        patterns = find_patterns(d["refunds_by_staff"], d["discounts_by_staff"], d["remakes_by_staff"])
        if not patterns:
            return {"quiet": True}
        csm = self.parts.directory.csm_of(ctx.task.area_id)
        client = next((a["name"] for a in self.parts.memory.areas() if a["area_id"] == ctx.task.area_id),
                      ctx.task.area_id)
        understood = {"client": client, "area_id": ctx.task.area_id, "csm_id": csm,
                      "as_of": d["refunds_by_staff"].get("as_of"), "window_days": WINDOW_DAYS, "patterns": patterns}
        ctx.notes["fraud_understood"] = understood
        return understood

    def decision_prompt(self, understood):
        return ("Below are unusual patterns found by code in the last "
                f"{understood['window_days']} days. Write each one for a DevX customer success manager in neutral words. "
                "Do not accuse anyone. Use only the ids and numbers shown.\n"
                f"{MARKER} {json.dumps(understood['patterns'], separators=(',', ':'))}\n"
                'Reply with final JSON only: {"patterns": [{"kind","staff_id","store_id","evidence","why_it_matters",'
                '"next_step"}], "followups": [{"staff_id","title"}]}. A follow-up waits for the manager\'s approval.')

    def parse_decision(self, final_text):
        start = final_text.index("{")
        decision, _ = json.JSONDecoder().raw_decode(final_text[start:])
        if not isinstance(decision.get("patterns"), list):
            raise ValueError("patterns must be a list")
        decision.setdefault("followups", [])
        return decision

    def check(self, ctx, decision, understood):
        problems = []
        known = {(p["kind"], p["staff_id"]): p for p in understood["patterns"]}
        allowed_ids = {p["staff_id"] for p in understood["patterns"]} | {p["store_id"] for p in understood["patterns"]}
        seen = set()
        for item in decision["patterns"]:
            key = (item.get("kind"), item.get("staff_id"))
            source = known.get(key)
            if source is None:
                problems.append(f"pattern {key} was not found by the code")
                continue
            seen.add(key)
            if item.get("store_id") != source["store_id"]:
                problems.append(f"store of {key} does not match the data")
            allowed_numbers = set(NUMBER.findall(json.dumps(source))) | set(NUMBER.findall(understood["as_of"] or ""))
            text = " ".join(str(item.get(k, "")) for k in ("evidence", "why_it_matters", "next_step"))
            extra = set(NUMBER.findall(text)) - allowed_numbers
            if extra:
                problems.append(f"numbers {sorted(extra)} for {key} are not in the data")
        for missing in sorted(set(known) - seen):
            problems.append(f"pattern {missing} found by the code is missing from the answer")
        for fu in decision["followups"]:
            if fu.get("staff_id") not in allowed_ids:
                problems.append(f"follow-up names {fu.get('staff_id')!r}, which is not in the data")
        everything = json.dumps(decision)
        for found in set(PERSON_OR_STORE.findall(everything)) - allowed_ids:
            problems.append(f"id {found} is not in the data")
        banned = sorted({m.group(0).lower() for m in BANNED.finditer(everything)})
        if banned:
            problems.append(f"banned words used: {banned}")
        problems += self._recipient_problems(ctx, understood, decision)
        return problems

    def _recipient_problems(self, ctx, understood, decision):
        csm = self.parts.directory.csm_of(ctx.task.area_id)
        if not csm or not self.parts.directory.is_devx(csm) or self.parts.directory.role(csm) != "csm":
            return [f"no DevX CSM found for area {ctx.task.area_id}"]
        if decision.get("to") not in (None, csm):
            return [f"recipient {decision.get('to')!r} is not the client's CSM {csm}"]
        return []

    def act(self, ctx, decision):
        understood = ctx.notes["fraud_understood"]
        csm = understood["csm_id"]
        calls = [ToolCall(id="fw-msg", name="send_private_message",
                          args={"to_person_id": csm, "text": self._message_text(understood, decision),
                                "kind": "unusual_pattern_review"})]
        titles = {}
        for fu in decision["followups"]:
            titles.setdefault((fu["staff_id"], fu["title"]), None)
        for i, (staff_id, title) in enumerate(titles, 1):
            calls.append(ToolCall(id=f"fw-fu-{i}", name="create_followup_task",
                                  args={"area_id": ctx.task.area_id, "title": title, "owner_id": csm}))
        return calls

    def _message_text(self, understood, decision):
        names = {(p["kind"], p["staff_id"]): p["staff_name"] for p in understood["patterns"]}
        lines = [f"Unusual patterns to review at {understood['client']} (last {understood['window_days']} days "
                 f"up to {understood['as_of']})."]
        for i, p in enumerate(decision["patterns"], 1):
            who = names.get((p["kind"], p["staff_id"])) or p["staff_id"]
            lines += [f"{i}. {who} ({p['staff_id']}), store {p['store_id']}: {p['evidence']}",
                      f"   Why it matters: {p['why_it_matters']}", f"   Next step: {p['next_step']}"]
        lines.append("These are unusual patterns, not conclusions. Store managers are client staff, so this note goes "
                     "to you to review and to talk with the store manager.")
        return "\n".join(lines)

    def remember(self, ctx, decision, acted):
        ids = [self.parts.memory.add_case(ctx.run_id, self.name, ctx.task.area_id,
                                          f"{p['kind']}: {p['staff_id']} at {p['store_id']}", "review",
                                          {"evidence": p["evidence"], "next_step": p["next_step"]})
               for p in decision["patterns"]]
        return {"cases": ids}
