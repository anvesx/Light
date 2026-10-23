"""Read tools for the deal brief: the deal's own area, similar redacted playbooks, and the kickoff checklist."""
import re

from control_plane.company_brain.retrieval import similar_deals

from .tool_reply import ToolInputError, build_tool, client_area_ids, int_arg, str_arg

SECTIONS = ("initially_wanted", "later_changed_to", "chose", "went_right", "went_wrong")
MIN_SCORE = 0.2
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE_RE = re.compile(r"\+?\d[\d\s-]{8,}\d")


def find_leaks(text, data_conn):
    """Contact names, emails and phone numbers in text. Uses the brain's redaction check when it exists."""
    try:
        from control_plane.company_brain.redaction import find_leaks as library_check
        return list(library_check(text, data_conn))
    except ImportError:
        pass
    names = [r["name"] for r in data_conn.execute("SELECT name FROM people WHERE is_devx = 0")]
    low = text.lower()
    return [n for n in names if n.lower() in low] + EMAIL_RE.findall(text) + PHONE_RE.findall(text)


def _entry(entry):
    """One playbook section entry as {"text", "topic"}; item ids of the source client are dropped."""
    if isinstance(entry, dict):
        return {"text": str(entry.get("text", "")), "topic": entry.get("topic")}
    return {"text": str(entry), "topic": None}


def playbook_view(pb):
    sections = {s: [_entry(e) for e in pb["sections"].get(s, [])] for s in SECTIONS}
    return {"playbook_id": pb["playbook_id"], "client_label": pb["client_label"], "industry": pb["industry"],
            "outcome": pb["outcome"], "tags": pb["tags"], "sections": sections}


def _brain(ctx, parts):
    return parts.brain.scoped(ctx.memory.area_ids)


def _deal(brain, area_id, deal_id):
    deal = next((d for d in brain.deals(area_id) if d["deal_id"] == deal_id), None)
    if deal is None:
        raise ToolInputError(f"deal {deal_id!r} is not in area {area_id!r}")
    return deal


def make_deal_overview(parts):
    def handler(args, area_id, as_of, ctx):
        brain = _brain(ctx, parts)
        deal = _deal(brain, area_id, str_arg(args, "deal_id"))
        items = [{"item_id": i["item_id"], "kind": i["kind"], "topic": i["topic"], "text": i["text"],
                  "confirmed": i["confirmed"],
                  "lines": [f"{e['source_id']}:{e['line_from']}-{e['line_to']}" for e in i["evidence"]]}
                 for i in brain.brain_items(area_id)]
        return {"deal": {k: deal[k] for k in ("deal_id", "area_id", "name", "industry", "stage", "value_inr", "tags")},
                "items": items}
    return build_tool(
        "deal_overview", "The deal and the items the brain holds for this deal's own area. Items may be unconfirmed.",
        {"deal_id": {"type": "string"}}, handler, area_ok=lambda a: a in client_area_ids(parts.data_conn),
        area_label="the deal's own client area", reads_outside_text=True)


def make_similar_playbooks(parts):
    def handler(args, area_id, as_of, ctx):
        brain = _brain(ctx, parts)
        deal = _deal(brain, area_id, str_arg(args, "deal_id"))
        by_id = {p["playbook_id"]: p for p in brain.playbooks()}
        ranked = [r for r in similar_deals(brain, deal, k=int_arg(args, "k", 3, 1, 10)) if r["score"] >= MIN_SCORE]
        return {"similar": [{**playbook_view(by_id[r["playbook_id"]]), "score": r["score"], "why": r["why"]}
                            for r in ranked]}
    return build_tool(
        "similar_playbooks", "The best matching redacted playbooks from the library, with five sections each.",
        {"deal_id": {"type": "string"}, "k": {"type": "integer"}}, handler,
        area_ok=lambda a: a in client_area_ids(parts.data_conn), area_label="the deal's own client area")


def make_kickoff_checklist(parts):
    def handler(args, area_id, as_of, ctx):
        brain = _brain(ctx, parts)
        deal_to_pb = {p["deal_id"]: p["playbook_id"] for p in brain.playbooks()}
        rows = brain.checklist(industry=str_arg(args, "industry"))
        return {"checklist": [{"check_id": c["checklist_id"], "topic": c["topic"], "question": c["question"],
                               "why": c["why"], "playbook_ids": [deal_to_pb[d] for d in c["learned_from"] if d in deal_to_pb]}
                              for c in rows]}
    return build_tool(
        "kickoff_checklist", "Questions to ask at kickoff, learned from requirements that came late in past projects.",
        {"industry": {"type": "string"}}, handler, area_ok=lambda a: a in client_area_ids(parts.data_conn),
        area_label="the deal's own client area")


def deal_brain_tools(parts):
    return [make_deal_overview(parts), make_similar_playbooks(parts), make_kickoff_checklist(parts)]
