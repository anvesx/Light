"""Deal brief pack: code picks similar playbooks and the checklist; the model writes ideas and questions; code checks every cite."""
import json

from control_plane.connectors.deal_brain_tools import deal_brain_tools, find_leaks
from contract.types import ToolCall
from lifecycle_kit.action_tools import make_send_private_message
from lifecycle_kit.agent_pack import AgentPack

CONTEXT_MARKER = "CONTEXT_JSON:\n"
RISK_KINDS = ("risk", "blocker", "question")

SYSTEM = ("You prepare a DevX growth person for a live deal. Use only the facts in the context: the deal's own items and "
          "the redacted playbooks. Name no client contact. Write for a person who is not an engineer.")
INSTRUCTIONS = (
    "Task: write the deal brief. Every idea, risk and question cites a playbook id (PB-...) or an item id of this deal. "
    "Label any item with confirmed false as Unconfirmed. Give each objection topic a closing idea and ask every checklist topic.\n"
    'Answer with final JSON only: {"deal_id": str, "similar": [], "closing_ideas": [{"text", "because", "cites", "topic"}], '
    '"risks": [{"text", "cites"}], "kickoff_questions": [{"topic", "question", "why", "cites"}], "summary": str}.\n')


def _read(ctx, name, args):
    """Run one read tool through the guard. Returns the parsed JSON, or {} when it was refused."""
    result = ctx.notes["invoke_tool"](name, args)["result"]
    start, end = result.find("{"), result.rfind("}")
    try:
        data = json.loads(result[start:end + 1])
    except ValueError:
        return {}
    return data if isinstance(data, dict) and "error" not in data else {}


class DealBriefPack(AgentPack):
    name = "deal_brief"
    starter_roles = frozenset({"growth", "ceo", "rnd_lead"})
    approver_roles = frozenset({"ceo"})
    reads_library = True

    def __init__(self, parts):
        self.parts = parts

    def tools(self):
        return [*deal_brain_tools(self.parts), make_send_private_message(self.parts.outbox)]

    def system_prompt(self):
        return SYSTEM

    def record(self, ctx):
        deal_id = ctx.task.inputs.get("deal_id")
        overview = _read(ctx, "deal_overview", {"deal_id": deal_id})
        if not overview:
            return {"error": f"deal {deal_id!r} not found in this area"}
        industry = overview["deal"]["industry"]
        return {"overview": overview,
                "similar": _read(ctx, "similar_playbooks", {"deal_id": deal_id, "k": 3}).get("similar", []),
                "checklist": _read(ctx, "kickoff_checklist", {"industry": industry}).get("checklist", [])}

    def understand(self, ctx, recorded):
        if "overview" not in recorded:
            return {"quiet": True}
        similar, deal = recorded["similar"], recorded["overview"]["deal"]
        shown = {p["playbook_id"] for p in similar}
        checklist = []
        for c in recorded["checklist"]:  # only questions learned from the similar clients
            ids = [p for p in c["playbook_ids"] if p in shown]
            if ids:
                checklist.append({**c, "playbook_ids": ids})
        items = recorded["overview"]["items"]
        wrong = [e["topic"] for p in similar for e in p["sections"]["went_wrong"] if e.get("topic")]
        objections = sorted(set(wrong) | {i["topic"] for i in items if i["kind"] in ("risk", "blocker") and i["topic"]})
        context = {"deal": deal, "items": items, "similar": similar, "checklist": checklist, "objection_topics": objections}
        ctx.notes["deal_brief"] = context
        return context

    def decision_prompt(self, understood):
        return INSTRUCTIONS + CONTEXT_MARKER + json.dumps(understood, separators=(",", ":"))

    def parse_decision(self, final_text):
        decision = json.loads(final_text[final_text.find("{"):final_text.rfind("}") + 1])
        for key in ("closing_ideas", "risks", "kickoff_questions"):
            if not isinstance(decision.get(key), list):
                raise ValueError(f"no {key} list")
        return decision

    def check(self, ctx, decision, understood):
        problems = []
        brain = self.parts.brain.scoped(ctx.memory.area_ids)
        library = {p["playbook_id"] for p in brain.playbooks()}
        unconfirmed = {i["item_id"] for i in understood["items"] if not i["confirmed"]}
        rows = [("idea", r, r.get("text")) for r in decision["closing_ideas"]]
        rows += [("risk", r, r.get("text")) for r in decision["risks"]]
        rows += [("question", r, r.get("question")) for r in decision["kickoff_questions"]]
        for n, (label, row, text) in enumerate(rows, 1):
            if not str(text or "").strip():
                problems.append(f"{label} {n} has no text")
            if not row.get("cites"):
                problems.append(f"{label} {n} cites nothing")
            for cite in row.get("cites") or []:
                if cite.startswith("PB-"):
                    if cite not in library:
                        problems.append(f"{label} {n} cites {cite!r}, which is not in the library")
                elif not self._own_item(brain, ctx.task.area_id, cite):
                    problems.append(f"{label} {n} cites {cite!r}, which is not an item of this deal's area")
            if unconfirmed & set(row.get("cites") or []) and "unconfirmed" not in json.dumps(row).lower():
                problems.append(f"{label} {n} rests on an unconfirmed item but is not labelled Unconfirmed")
        asked = {q.get("topic") for q in decision["kickoff_questions"]}
        for c in understood["checklist"]:
            if c["topic"] not in asked:
                problems.append(f"checklist topic {c['topic']!r} is not asked")
        covered = {r.get("topic") for r in decision["closing_ideas"]}
        for topic in understood["objection_topics"]:
            if topic not in covered:
                problems.append(f"objection topic {topic!r} has no closing idea")
        own = understood["deal"]["name"].lower()  # the deal's own client name is fine to say
        leaks = [x for x in find_leaks(json.dumps(decision), self.parts.data_conn) if x.lower() not in (own, own.split()[0])]
        if leaks:
            problems.append(f"the brief names a client contact or contact detail: {leaks[0]!r}")
        return problems

    @staticmethod
    def _own_item(brain, area_id, item_id):
        try:
            item = brain.get_brain_item(item_id)
        except Exception:  # AreaDenied for another area
            return False
        return item is not None and item["area_id"] == area_id

    def act(self, ctx, decision):
        caller = ctx.task.caller_id
        if caller == "system" or not self.parts.directory.is_devx(caller):
            return []
        return [ToolCall("brief-1", "send_private_message",
                         {"to_person_id": caller, "kind": "deal_brief", "text": self.brief_text(ctx.notes["deal_brief"], decision)})]

    @staticmethod
    def brief_text(context, decision):
        lines = [f"Deal brief: {context['deal']['name']} ({context['deal']['stage']})", decision.get("summary", ""), ""]
        for title, key, field in (("Ideas to close", "closing_ideas", "text"), ("Risks", "risks", "text"),
                                  ("Ask at kickoff", "kickoff_questions", "question")):
            lines.append(title + ":")
            lines += [f"- {r[field]} ({', '.join(r['cites'])})" for r in decision[key]]
            lines.append("")
        return "\n".join(lines).strip()

    def remember(self, ctx, decision, acted):
        return {"topics_asked": sorted({q["topic"] for q in decision["kickoff_questions"] if q.get("topic")}),
                "briefs_sent": sum(1 for a in acted if a["verdict"] == "allow")}


def make_pack(parts) -> DealBriefPack:
    return DealBriefPack(parts)
