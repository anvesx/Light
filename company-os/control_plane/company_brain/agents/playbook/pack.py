"""Playbook writer pack: turn a closed deal into a redacted playbook and kickoff checklist questions in the library."""
import json

from control_plane.company_brain import link_tools, playbook_rules
from control_plane.company_brain.redaction import find_leaks
from control_plane.company_brain.topic_lexicon import load_lexicon
from lifecycle_kit.agent_pack import AgentPack

CONTEXT_MARKER = "CONTEXT_JSON:\n"
SYSTEM = ("You write a redacted playbook of a closed deal for the company library. Use only the context. "
          "Never write a person's name, an email address, a phone number or pay details.")
INSTRUCTIONS = ("Task: return the playbook as given, with clearer wording if you can. Keep every item id and topic. "
                'Answer with final JSON only: {"client_label": str, "revenue_inr": int, "sections": {...}, "tags": [str], '
                '"checklist": [{"topic": str, "question": str, "why": str, "learned_from": [str], "industries": [str]}]}.\n')


def _unwrap(result):
    start, end = result.find("{"), result.rfind("}")
    return json.loads(result[start:end + 1]) if 0 <= start < end else {}


class PlaybookPack(AgentPack):
    name = "brain_playbook"
    starter_roles = frozenset({"system", "ceo", "rnd_lead", "finance_lead", "growth"})
    approver_roles = frozenset({"ceo"})

    def __init__(self, parts):
        self.parts = parts

    def tools(self):
        b = self.parts.brain
        return [link_tools.make_read_deal(b, self.parts.data_conn), link_tools.make_publish_playbook(b),
                link_tools.make_save_checklist(b)]

    def system_prompt(self):
        return SYSTEM

    def record(self, ctx):
        read, deal_id = ctx.notes["invoke_tool"], ctx.task.inputs.get("deal_id")
        data = _unwrap(read("brain_read_deal", {"deal_id": deal_id})["result"])
        if "deal" not in data:
            return {"error": data.get("error", "no deal")}
        offset = len(data["items"])
        while offset < data["total"]:
            page = _unwrap(read("brain_read_deal", {"deal_id": deal_id, "offset": offset})["result"])
            data["items"] += page.get("items", [])
            offset += max(len(page.get("items", [])), 1)
        return data

    def understand(self, ctx, recorded):
        if not recorded or "deal" not in recorded or recorded["deal"]["stage"] not in ("won", "lost"):
            return {"quiet": True}
        plan = playbook_rules.build(recorded, self.parts.data_conn)
        ctx.notes["playbook"] = {"deal_id": recorded["deal"]["deal_id"], "item_ids": {i["item_id"] for i in recorded["items"]}}
        return {"deal_id": recorded["deal"]["deal_id"], "outcome": recorded["deal"]["stage"], **plan}

    def decision_prompt(self, understood):
        return INSTRUCTIONS + CONTEXT_MARKER + json.dumps(understood, separators=(",", ":"))

    def parse_decision(self, final_text):
        start, end = final_text.find("{"), final_text.rfind("}")
        decision = json.loads(final_text[start:end + 1])
        if not isinstance(decision.get("sections"), dict):
            raise ValueError("no sections")
        decision.setdefault("checklist", [])
        return decision

    def check(self, ctx, decision, understood):
        problems, known = [], ctx.notes["playbook"]["item_ids"]
        topics = set(load_lexicon().get("topics", {}))
        if set(decision["sections"]) != set(playbook_rules.SECTIONS):
            problems.append("the sections are not the five playbook sections")
        for name, entries in decision["sections"].items():
            for e in entries:
                if not e.get("item_ids") or not set(e["item_ids"]) <= known:
                    problems.append(f"an entry in {name} does not cite items of its own area")
                if e.get("topic") and topics and e["topic"] not in topics:
                    problems.append(f"topic {e['topic']!r} is not in the lexicon")
        plan = {"client_label": decision.get("client_label", ""), "sections": decision["sections"], "checklist": decision["checklist"]}
        leaks = sorted({leak for t in playbook_rules.texts_of(plan) for leak in find_leaks(t, self.parts.data_conn)})
        if leaks:
            problems.append(f"the playbook leaks private details: {', '.join(leaks)}")
        return problems

    def act(self, ctx, decision):
        deal_id = ctx.notes["playbook"]["deal_id"]
        calls = [("brain_publish_playbook", {"deal_id": deal_id, "sections": decision["sections"], "tags": decision["tags"],
                                             "client_label": decision["client_label"], "revenue_inr": decision.get("revenue_inr", 0)})]
        if decision["checklist"]:
            calls.append(("brain_save_checklist", {"items": decision["checklist"]}))
        return calls

    def remember(self, ctx, decision, acted):
        return {"entries": sum(len(v) for v in decision["sections"].values()), "checklist": len(decision["checklist"])}


def make_pack(parts) -> PlaybookPack:
    return PlaybookPack(parts)
