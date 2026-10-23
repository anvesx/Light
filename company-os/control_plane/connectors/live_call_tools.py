"""Read tools for a live call: the call script and the brain view (open items, decisions, checklist) for its client."""
import json
import os

from control_plane.company_brain.scoped_brain import AreaDenied
from company_data import DB_PATH

from .tool_reply import ToolInputError, build_tool, client_area_ids, str_arg

LIVE_DIR = os.path.join(os.path.dirname(DB_PATH), "brain_sources", "live_calls")
TRANSLATIONS = os.path.join(os.path.dirname(DB_PATH), "brain_sources", "translations.json")
PARTS = ("open_items", "decisions", "checklist")
LIMIT = 22


def _load_lines(call_id):
    path = os.path.join(LIVE_DIR, f"{call_id}.jsonl")
    if not call_id.isalnum() or not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def _translations():
    try:
        with open(TRANSLATIONS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def load_call(data_conn, call_id):
    """Describe one simulated call: area (the client contact's client), the DevX viewer, lines with clean English."""
    lines = _load_lines(call_id) if isinstance(call_id, str) else None
    if not lines:
        return None
    people = {r["person_id"]: dict(r) for r in data_conn.execute("SELECT person_id, name, client_id, is_devx FROM people")}
    ids = {l["speaker_id"] for l in lines}
    client = next((people[i] for i in sorted(ids) if i in people and not people[i]["is_devx"]), None)
    devx = next((i for i in sorted(ids) if i in people and people[i]["is_devx"]), None)
    if client is None or devx is None:
        return None
    trans = _translations()
    for l in lines:
        l["clean_text"] = l["text"] if l.get("lang") == "en" else trans.get(f"{call_id}:{l['line_no']}", l["text"])
    row = data_conn.execute("SELECT name, industry FROM clients WHERE client_id = ?", (client["client_id"],)).fetchone()
    return {"call_id": call_id, "area_id": client["client_id"], "viewer_id": devx, "client_name": row["name"],
            "industry": row["industry"], "title": f"{people[devx]['name']} with {row['name']}", "lines": lines}


def list_calls(data_conn):
    out = []
    for name in sorted(os.listdir(LIVE_DIR)):
        if name.endswith(".jsonl"):
            call = load_call(data_conn, name[:-6])
            if call:
                out.append({k: v for k, v in call.items() if k != "lines"} | {"line_count": len(call["lines"]),
                                                                                "seconds": call["lines"][-1]["t_sec"]})
    return out


def make_live_call_script(data_conn):
    def handler(args, area_id, as_of, ctx):
        call = load_call(data_conn, str_arg(args, "call_id") or ctx.task.inputs.get("call_id"))
        if call is None:
            raise ToolInputError("unknown call")
        if call["area_id"] != area_id:
            raise ToolInputError(f"call {call['call_id']!r} is not in area {area_id!r}")
        return call
    return build_tool("live_call_script", "The simulated call: title, client, industry and its lines (original and English).",
                      {"call_id": {"type": "string"}}, handler,
                      area_ok=lambda a: a in client_area_ids(data_conn), area_label="a client area", reads_outside_text=True)


def _view(item, brain, cache):
    ev = (item["evidence"] or [{}])[0]
    sid = ev.get("source_id")
    if sid not in cache:
        cache[sid] = brain.get_source(sid) or {}
    src = cache[sid]
    return {"item_id": item["item_id"], "kind": item["kind"], "topic": item["topic"], "text": item["text"][:150], "source_id": sid,
            "origin_ref": src.get("origin_ref"), "source_kind": src.get("kind"), "occurred_at": src.get("occurred_at"),
            "line_from": ev.get("line_from")}


def make_live_call_brain(data_conn, brain):
    def handler(args, area_id, as_of, ctx):
        part = str_arg(args, "part")
        if part not in PARTS:
            raise ToolInputError(f"part must be one of {', '.join(PARTS)}")
        scoped = brain.scoped(ctx.memory.area_ids)
        if part == "checklist":
            industry = data_conn.execute("SELECT industry FROM clients WHERE client_id = ?", (area_id,)).fetchone()["industry"]
            try:
                rows = scoped.checklist(industry=industry)
            except AreaDenied:
                rows = []  # a CSM run has no library
            return {"part": part, "items": rows[:LIMIT]}
        kinds = ["decision"] if part == "decisions" else ["requirement", "question", "blocker", "risk", "sentiment"]
        cache = {}
        items = scoped.brain_items(area_id, kinds=kinds)
        if part == "open_items":  # the newest item per topic and kind keeps the reply small
            items = list({(i["topic"], i["kind"]): i for i in items}.values())
        return {"part": part, "items": [_view(i, scoped, cache) for i in items][-LIMIT:]}
    return build_tool("live_call_brain", "What the brain holds for this client: open_items, decisions, or the kickoff checklist.",
                      {"part": {"type": "string", "description": "open_items, decisions or checklist"}}, handler,
                      area_ok=lambda a: a in client_area_ids(data_conn), area_label="a client area", reads_outside_text=True)


def live_call_tools(data_conn, brain):
    return [make_live_call_script(data_conn), make_live_call_brain(data_conn, brain)]
