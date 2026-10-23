"""Tools for the Linker and Playbook writer. None is risky; each refuses items and sources outside the run's area."""
import json

from contract.types import ToolSpec

from .brain_store import STATES
from .link_rules import scope_for
from .retrieval import _group

RELS = ("supersedes", "answers", "refines", "follows_up", "contradicts", "same_as")
LATE_STATES = ("superseded", "resolved")


def _out(obj):
    return json.dumps(obj, separators=(",", ":"), default=str)


def _own_item(brain, item_id, area_id):
    item = brain.get_brain_item(item_id)
    if item is None or item["area_id"] != area_id:
        raise ValueError(f"item {item_id!r} is not in area {area_id!r}")
    return item


def _guard(fn):
    def run(args, ctx):
        try:
            return _out(fn(args or {}, ctx))
        except (ValueError, KeyError) as e:
            return _out({"error": str(e)})
    return run


def _has_link(brain, a, rel, b):
    return any(l["from_id"] == a and l["rel"] == rel and l["to_id"] == b for l in brain.memory.links_of(a))


def make_read_source_items(brain):
    def fn(args, ctx):
        area = ctx.task.area_id
        source = brain.get_source(args.get("source_id"))
        if source is None or source["area_id"] != area:
            raise ValueError("that source is not in this area")
        rows = []
        for i in brain.brain_items([area], state="active"):
            facts = i["facts"]
            src = brain.get_source(facts["source_id"])
            ev = i["evidence"][0] if i["evidence"] else {"line_from": 0, "line_to": 0}
            rows.append({"item_id": i["item_id"], "kind": i["kind"], "topic": i["topic"], "text": i["text"], "state": i["state"],
                         "project_id": facts.get("project_id"), "deal_id": facts.get("deal_id"), "source_id": facts["source_id"],
                         "line_from": ev["line_from"], "line_to": ev["line_to"],
                         "when": facts.get("said_at") or src["occurred_at"] or src["received_at"] or i["created_at"]})
        topics = {r["topic"] for r in rows if r["source_id"] == source["source_id"]}
        rows = [r for r in rows if r["source_id"] == source["source_id"] or r["topic"] in topics]  # keep the reply small
        links = [[l["from_id"], l["rel"], l["to_id"]] for i in rows for l in brain.memory.links_of(i["item_id"])]
        return {"source": {k: source[k] for k in ("source_id", "title", "project_id", "deal_id", "area_id")}, "items": rows,
                "links": links, "projects": [{"project_id": p["project_id"], "name": p["name"]} for p in brain.projects([area])],
                "deals": [{"deal_id": d["deal_id"]} for d in brain.deals([area])]}
    return ToolSpec("brain_read_source_items", "Read the live items of this area, the links between them and the area's projects and deals.",
                    {"type": "object", "required": ["source_id"], "properties": {"source_id": {"type": "string"}}},
                    _guard(fn), reads_outside_text=True)


def make_set_scope(brain):
    def fn(args, ctx):
        done = 0
        for a in args["assignments"]:
            item = _own_item(brain, a["item_id"], ctx.task.area_id)
            brain.set_scope(item["item_id"], project_id=a.get("project_id"), deal_id=a.get("deal_id"))
            done += 1
        return {"scoped": done}
    return ToolSpec("brain_set_scope", "Set the project and deal of items in this area.",
                    {"type": "object", "required": ["assignments"], "properties": {"assignments": {"type": "array"}}}, _guard(fn))


def make_add_links(brain):
    def fn(args, ctx):
        area, added, skipped = ctx.task.area_id, 0, 0
        for l in args["links"]:
            a, b, rel = l["from"], l["to"], l["rel"]
            if rel not in RELS:
                raise ValueError(f"unknown link {rel!r}")
            _own_item(brain, a, area), _own_item(brain, b, area)
            if _has_link(brain, a, rel, b):
                skipped += 1
                continue
            if rel == "contradicts":
                brain.resolve_contradiction(a, b)  # the newer wins, the older becomes superseded
            else:
                brain.memory.add_link(a, rel, b)
                if rel == "supersedes":
                    brain.set_state(b, "superseded")
                elif rel == "answers" and _own_item(brain, b, area)["state"] in ("active", "unconfirmed"):
                    brain.set_state(b, "resolved")
                elif rel == "same_as":  # the older item keeps the evidence of the repeat
                    have = {(e["source_id"], e["line_from"], e["line_to"]) for e in brain.get_brain_item(b)["evidence"]}
                    for e in brain.get_brain_item(a)["evidence"]:
                        if (e["source_id"], e["line_from"], e["line_to"]) not in have:
                            brain.add_evidence(b, e["source_id"], e["line_from"], e["line_to"], e["quote_raw"], e["quote_clean"])
                    brain.set_state(a, "resolved")
            added += 1
        return {"added": added, "skipped": skipped}
    return ToolSpec("brain_add_links", "Add links between items of this area. Each link is {from, rel, to}; from is the newer item.",
                    {"type": "object", "required": ["links"], "properties": {"links": {"type": "array"}}}, _guard(fn))


def make_set_state(brain):
    def fn(args, ctx):
        if args["state"] not in STATES:
            raise ValueError(f"unknown state {args['state']!r}")
        _own_item(brain, args["item_id"], ctx.task.area_id)
        brain.set_state(args["item_id"], args["state"])
        return {"item_id": args["item_id"], "state": args["state"]}
    return ToolSpec("brain_set_state", "Set the state of one item of this area.",
                    {"type": "object", "required": ["item_id", "state"],
                     "properties": {"item_id": {"type": "string"}, "state": {"type": "string"}}}, _guard(fn))


def make_read_deal(brain, data_conn):
    """Everything the Playbook writer reads about one closed deal of this area. Items come in pages of 20."""
    def fn(args, ctx):
        area = ctx.task.area_id
        deal = next((d for d in brain.deals([area]) if d["deal_id"] == args.get("deal_id")), None)
        if deal is None:
            raise ValueError("that deal is not in this area")
        offset = int(args.get("offset", 0))
        rows = []
        for i in brain.brain_items([area], state=None):
            if i["state"] == "dropped":
                continue
            src = brain.get_source(i["facts"]["source_id"])
            answered = any(l["rel"] == "answers" and l["to_id"] == i["item_id"] for l in brain.memory.links_of(i["item_id"]))
            rows.append({"item_id": i["item_id"], "kind": i["kind"], "topic": i["topic"], "text": i["text"][:200],
                         "state": i["state"], "when": (i["facts"].get("said_at") or src["occurred_at"] or src["received_at"])[:10],
                         "answered": answered})
        page = {"total": len(rows), "items": rows[offset:offset + 20]}
        if offset:
            return page
        lead = data_conn.execute("SELECT * FROM leads WHERE lead_id = ?", (deal["deal_id"],)).fetchone()
        last_call = data_conn.execute("SELECT MAX(date) AS d FROM growth_calls WHERE lead_id = ?", (deal["deal_id"],)).fetchone()["d"]
        projects = brain.projects([area])
        project = next((p for p in projects if p["project_id"] == "PR" + deal["deal_id"][1:]), projects[0] if projects else None)
        revenue = [r for r in brain.revenue([area]) if project is None or r["project_id"] == project["project_id"]]
        return {**page, "deal": deal, "area_id": area, "won_on": lead["won_on"] if lead else None, "last_call": last_call,
                "lost_reason": lead["lost_reason"] if lead else None, "project": project,
                "revenue_inr": sum(r["amount_inr"] for r in revenue)}
    return ToolSpec("brain_read_deal", "Read a closed deal of this area: its dates, project, revenue and items (20 per page).",
                    {"type": "object", "required": ["deal_id"],
                     "properties": {"deal_id": {"type": "string"}, "offset": {"type": "integer"}}},
                    _guard(fn), reads_outside_text=True)


def make_publish_playbook(brain):
    def fn(args, ctx):
        area = ctx.task.area_id
        deal = next((d for d in brain.deals([area]) if d["deal_id"] == args["deal_id"]), None)
        if deal is None or deal["stage"] not in ("won", "lost"):
            raise ValueError("only a won or lost deal of this area gets a playbook")
        for entries in args["sections"].values():
            for e in entries:
                for item_id in e["item_ids"]:
                    _own_item(brain, item_id, area)
        pid = brain.save_playbook(source_area_id=area, deal_id=deal["deal_id"], client_label=args["client_label"],
                                  industry=deal["industry"], outcome=deal["stage"], revenue_inr=args.get("revenue_inr", 0),
                                  sections=args["sections"], tags=args["tags"], run_id=ctx.run_id)
        return {"playbook_id": pid}
    return ToolSpec("brain_publish_playbook", "Save the redacted playbook of a closed deal to the library. Takes no area.",
                    {"type": "object", "required": ["deal_id", "sections", "tags", "client_label"],
                     "properties": {"deal_id": {"type": "string"}, "sections": {"type": "object"}, "tags": {"type": "array"},
                                    "client_label": {"type": "string"}, "revenue_inr": {"type": "integer"}}}, _guard(fn))


def make_save_checklist(brain):
    def fn(args, ctx):
        saved = []
        for c in args["items"]:
            old = next((x for x in brain.checklist() if x["topic"] == c["topic"] and x["question"] == c["question"]), None)
            learned = sorted(set(c["learned_from"]) | set(old["learned_from"] if old else []))
            industries = sorted(set(c["industries"]) | set(old["industries"] if old else []))
            saved.append(brain.save_checklist_item(topic=c["topic"], question=c["question"], why=c["why"],
                                                   learned_from=learned, industries=industries))
        return {"saved": saved}
    return ToolSpec("brain_save_checklist", "Save kickoff checklist questions to the library. Takes no area.",
                    {"type": "object", "required": ["items"], "properties": {"items": {"type": "array"}}}, _guard(fn))


def industries_of(industry):
    return sorted(_group(industry) or {industry}) if industry else []
