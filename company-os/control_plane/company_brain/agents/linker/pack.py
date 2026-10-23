"""Linker pack: connect the new items of one source to older items, projects and deals. Code decides; the model confirms."""
import json

from control_plane.company_brain import link_rules, link_tools
from lifecycle_kit.agent_pack import AgentPack

CONTEXT_MARKER = "CONTEXT_JSON:\n"
SYSTEM = ("You check links between facts in a client's company memory. Use only the context. "
          "Answer for each unsure pair only if you are sure of the relation.")
INSTRUCTIONS = ('Task: confirm the planned links. For each unsure pair you may add one link of type supersedes, refines, same_as, '
                'answers, follows_up or contradicts, or leave it out. Answer with final JSON only: '
                '{"links": [{"from": id, "rel": str, "to": id}], "scope": [{"item_id": id, "project_id": str|null, "deal_id": str|null}]}.\n')


def _unwrap(result):
    start, end = result.find("{"), result.rfind("}")
    return json.loads(result[start:end + 1]) if 0 <= start < end else {}


class LinkerPack(AgentPack):
    name = "brain_linker"
    starter_roles = frozenset({"system", "ceo", "rnd_lead", "finance_lead", "csm", "growth"})
    approver_roles = frozenset({"ceo"})

    def __init__(self, parts):
        self.parts = parts

    def tools(self):
        b = self.parts.brain
        return [link_tools.make_read_source_items(b), link_tools.make_set_scope(b), link_tools.make_add_links(b),
                link_tools.make_set_state(b)]

    def system_prompt(self):
        return SYSTEM

    def record(self, ctx):
        data = _unwrap(ctx.notes["invoke_tool"]("brain_read_source_items", {"source_id": ctx.task.inputs.get("source_id")})["result"])
        return data if "items" in data else {"error": data.get("error", "no data")}

    def understand(self, ctx, recorded):
        if not recorded or "items" not in recorded:
            return {"quiet": True}
        source_id = recorded["source"]["source_id"]
        new = [i for i in recorded["items"] if i["source_id"] == source_id]
        others = [i for i in recorded["items"] if i["source_id"] != source_id]
        existing = {tuple(l) for l in recorded["links"]}
        plan = link_rules.plan_links(new, others, existing)
        scope = []
        for i in new:
            project, deal = link_rules.scope_for(recorded["source"], i, recorded["projects"], recorded["deals"])
            if (project, deal) != (i["project_id"], i["deal_id"]) and (project or deal):
                scope.append({"item_id": i["item_id"], "project_id": project, "deal_id": deal})
        if not plan["links"] and not scope and not plan["unsure"]:
            return {"quiet": True}
        ids = {i["item_id"]: i for i in recorded["items"]}
        ctx.notes["linker"] = {"ids": set(ids), "unsure": {frozenset((u["a"], u["b"])) for u in plan["unsure"]}, "items": ids,
                               "planned": {(l["from"], l["rel"], l["to"]) for l in plan["links"]}}
        return {"source_id": source_id, "links": plan["links"], "scope": scope, "unsure": plan["unsure"],
                "items": [{k: i[k] for k in ("item_id", "kind", "topic", "text")} for i in recorded["items"]
                          if any(i["item_id"] in (u["a"], u["b"]) for u in plan["unsure"])]}

    def decision_prompt(self, understood):
        return INSTRUCTIONS + CONTEXT_MARKER + json.dumps(understood, separators=(",", ":"))

    def parse_decision(self, final_text):
        start, end = final_text.find("{"), final_text.rfind("}")
        decision = json.loads(final_text[start:end + 1])
        if not isinstance(decision.get("links"), list):
            raise ValueError("no links list")
        decision.setdefault("scope", [])
        return decision

    def check(self, ctx, decision, understood):
        note, problems = ctx.notes["linker"], []
        for l in decision["links"]:
            if l.get("rel") not in link_tools.RELS:
                problems.append(f"unknown link type {l.get('rel')!r}")
            elif l.get("from") not in note["ids"] or l.get("to") not in note["ids"] or l["from"] == l["to"]:
                problems.append(f"link {l} uses an item outside this area")
            elif (l["from"], l["rel"], l["to"]) not in note["planned"] and frozenset((l["from"], l["to"])) not in note["unsure"]:
                problems.append(f"link {l} was not planned and is not an unsure pair")
        for s in decision["scope"]:
            if s.get("item_id") not in note["ids"]:
                problems.append(f"scope for {s.get('item_id')!r} is outside this area")
        return problems

    def act(self, ctx, decision):
        calls = []
        if decision["scope"]:
            calls.append(("brain_set_scope", {"assignments": decision["scope"]}))
        if decision["links"]:
            calls.append(("brain_add_links", {"links": decision["links"]}))
        return calls

    def remember(self, ctx, decision, acted):
        return {"links": len(decision["links"]), "scoped": len(decision["scope"])}


def make_pack(parts) -> LinkerPack:
    return LinkerPack(parts)
