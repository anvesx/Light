"""Read tool for the project brief: brain items of one project with their source lines, read through a scoped brain."""
from control_plane.guardrails.role_scopes import DB_ROLE_TO_CONSOLE, may_see

from .tool_reply import ToolInputError, build_tool, client_area_ids, str_arg

KINDS = ("question", "requirement", "blocker", "decision", "commitment", "risk")
CLOSING = ("supersedes", "contradicts")


def source_day(source):
    return (source.get("occurred_at") or source.get("received_at") or "")[:10]


def item_view(sb, item):
    """One brain item as plain JSON: text, state and every source line it rests on."""
    sources = []
    for ev in item["evidence"]:
        src = sb.get_source(ev["source_id"]) or {}
        sources.append({"source_id": ev["source_id"], "origin_ref": src.get("origin_ref"), "title": src.get("title"),
                        "date": source_day(src), "line_from": ev["line_from"], "line_to": ev["line_to"],
                        "quote": ev["quote_clean"] or ev["quote_raw"]})
    return {"item_id": item["item_id"], "kind": item["kind"], "text": item["text"], "topic": item["topic"],
            "state": item["state"], "unconfirmed": item["state"] == "unconfirmed",
            "said_at": sources[0]["date"] if sources else "", "sources": sources}


def compact(view, info):
    """Short form for the model: source facts move to one shared table (tool output is capped at 8000 characters)."""
    out = {k: view[k] for k in ("item_id", "kind", "text", "topic", "unconfirmed")}
    out["sources"] = []
    for s in view["sources"]:
        info[s["source_id"]] = {k: s[k] for k in ("origin_ref", "title", "date")}
        out["sources"].append({k: s[k] for k in ("source_id", "line_from", "line_to")})
    return out


def _answered(memory, item_id):
    return any(l["to_id"] == item_id and l["rel"] == "answers" for l in memory.links_of(item_id))


def _changes(sb, memory, project_id, as_of):
    out = []
    for old in sb.brain_items(None, state="superseded", project_id=project_id):
        for link in memory.links_of(old["item_id"]):
            if link["to_id"] != old["item_id"] or link["rel"] not in CLOSING:
                continue
            new = sb.get_brain_item(link["from_id"])
            if new is None:
                continue
            old_v, new_v = item_view(sb, old), item_view(sb, new)
            if new_v["said_at"] <= as_of:
                out.append({"old": old_v, "new": new_v, "changed_on": new_v["said_at"]})
    return sorted(out, key=lambda c: c["changed_on"])


def _sees_deal_stage(data_conn, person_id):
    row = data_conn.execute("SELECT role FROM people WHERE person_id = ?", (person_id,)).fetchone()
    return bool(row) and may_see(DB_ROLE_TO_CONSOLE.get(row["role"]), "deal_items")


def make_project_brain_items(data_conn, brain):
    def handler(args, area_id, as_of, ctx):
        project_id = str_arg(args, "project_id")
        if not project_id:
            raise ToolInputError("project_id is required")
        kinds = args.get("kinds") or list(KINDS)
        if not isinstance(kinds, list) or not all(isinstance(k, str) for k in kinds):
            raise ToolInputError("kinds must be a list of text")
        if brain is None:
            return {"as_of": as_of, "items": [], "changes": [], "unconfirmed_count": 0}
        hide = not _sees_deal_stage(data_conn, ctx.task.caller_id)  # PLAN 5: deal talk is for Admin and Growth only
        sb, memory = brain.scoped(ctx.memory.area_ids, hide_deal_stage=hide), ctx.memory
        items, info = [], {}
        for raw in sb.brain_items(area_id, kinds=kinds, project_id=project_id):
            view = item_view(sb, raw)
            if view["said_at"] <= as_of and not (raw["kind"] == "question" and _answered(memory, raw["item_id"])):
                items.append(compact(view, info))
        changes = [{"old": compact(c["old"], info), "new": compact(c["new"], info), "changed_on": c["changed_on"]}
                   for c in _changes(sb, memory, project_id, as_of) if c["new"]["kind"] in kinds]
        return {"as_of": as_of, "items": items, "changes": changes, "source_info": info,
                "unconfirmed_count": sb.unconfirmed_count(area_id, project_id)}
    return build_tool(
        "project_brain_items",
        "Brain items of one project (questions, requirements, blockers, decisions, commitments, risks) with the source "
        "lines they come from, decisions that changed, and the number of unconfirmed items.",
        {"project_id": {"type": "string"}, "kinds": {"type": "array", "items": {"type": "string"}}}, handler,
        area_ok=lambda a: a in client_area_ids(data_conn), area_label="a client area", reads_outside_text=True)
