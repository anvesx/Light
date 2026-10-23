"""Tools for the brain agents: read a source, save clean lines, add items, queue review rows. None is risky."""
import json

from contract.types import ToolSpec

PAGE_LINES = 25  # a read returns at most this many lines, so one result fits the tool output cap
REASON_UNTRANSLATED = "no English version of this line; raw text kept"


def _own_source(brain, ctx, source_id):
    source = brain.get_source(source_id)
    if source is None:
        raise ValueError(f"unknown source {source_id!r}")
    if source["area_id"] != ctx.task.area_id:
        raise ValueError(f"source {source_id} is not in area {ctx.task.area_id}")
    return source


def untranslated_lines(brain, source):
    """Line numbers the Cleaner could not translate: pending or decided translation rows with no item."""
    rows = brain.reviews([source["area_id"]], status=None)
    return sorted({r["proposed"]["line_no"] for r in rows
                   if r["source_id"] == source["source_id"] and r["kind"] == "translation" and not r["item_id"]})


def make_read_source(brain) -> ToolSpec:
    def fn(args, ctx):
        source = _own_source(brain, ctx, args["source_id"])
        lines = brain.source_lines(source["source_id"])
        start = int(args.get("from_line", 1))
        page = [l for l in lines if l["line_no"] >= start][:PAGE_LINES]
        skipped = set(untranslated_lines(brain, source))
        return json.dumps({
            "source_id": source["source_id"], "origin_ref": source["origin_ref"], "title": source["title"],
            "kind": source["kind"], "language": source["language"], "participants": source["participants"],
            "occurred_at": source["occurred_at"], "status": source["status"], "total_lines": len(lines),
            "next_line": page[-1]["line_no"] + 1 if page and page[-1]["line_no"] < lines[-1]["line_no"] else None,
            "lines": [{**l, "untranslated": l["line_no"] in skipped} for l in page]})
    return ToolSpec(
        name="brain_read_source", description="Read the lines of one source of this area, 25 lines at a time.",
        params={"type": "object", "required": ["source_id"], "properties": {
            "source_id": {"type": "string"}, "from_line": {"type": "integer"}}},
        fn=fn, reads_outside_text=True)


def make_save_clean_lines(brain) -> ToolSpec:
    def fn(args, ctx):
        source = _own_source(brain, ctx, args["source_id"])
        brain.set_clean_lines(source["source_id"], args["lines"])
        brain.set_source_status(source["source_id"], "cleaned")
        return f"saved {len(args['lines'])} clean lines"
    return ToolSpec(
        name="brain_save_clean_lines", description="Save clean English text and speaker names. Raw text never changes.",
        params={"type": "object", "required": ["source_id", "lines"], "properties": {
            "source_id": {"type": "string"}, "lines": {"type": "array"}}}, fn=fn)


def make_add_items(brain) -> ToolSpec:
    def fn(args, ctx):
        source = _own_source(brain, ctx, args["source_id"])
        by_line = {l["line_no"]: l for l in brain.source_lines(source["source_id"])}
        untranslated = set(untranslated_lines(brain, source))
        ids = []
        for item in args["items"]:
            span = range(item["line_from"], item["line_to"] + 1)
            raw = " ".join(by_line[n]["text"] for n in span)
            clean = " ".join((by_line[n]["clean_text"] or by_line[n]["text"]) for n in span)
            gap = any(n in untranslated for n in span)
            ids.append(brain.add_brain_item(
                source["area_id"], item["kind"], item["text"], topic=item["topic"], source_id=source["source_id"],
                line_from=item["line_from"], line_to=item["line_to"], quote_raw=raw, quote_clean=clean,
                confidence=item["confidence"], project_id=source["project_id"], deal_id=source["deal_id"],
                said_at=source["occurred_at"], value=item.get("value"),
                state="unconfirmed" if gap else None, review_kind="translation" if gap else "low_confidence"))
        brain.set_source_status(source["source_id"], "extracted")
        return f"stored {len(ids)} items: {', '.join(ids)}"
    return ToolSpec(
        name="brain_add_items", description="Store items with their source lines. Low confidence is stored as unconfirmed.",
        params={"type": "object", "required": ["source_id", "items"], "properties": {
            "source_id": {"type": "string"}, "items": {"type": "array"}}}, fn=fn)


def make_queue_review(brain) -> ToolSpec:
    def fn(args, ctx):
        source = _own_source(brain, ctx, args["source_id"])
        ids = [brain.queue_review(source["area_id"], source["source_id"], p, p.get("reason", REASON_UNTRANSLATED),
                                  p.get("confidence"), kind=p.get("kind", "translation")) for p in args["proposals"]]
        return f"queued {len(ids)} review rows"
    return ToolSpec(
        name="brain_queue_review", description="Add rows to the optional check list. Nothing waits on them.",
        params={"type": "object", "required": ["source_id", "proposals"], "properties": {
            "source_id": {"type": "string"}, "proposals": {"type": "array"}}}, fn=fn)


def brain_write_tools(brain):
    return [make_read_source(brain), make_save_clean_lines(brain), make_add_items(brain), make_queue_review(brain)]


def read_whole_source(invoke_tool, source_id):
    """Read every page of a source through the guarded tool call. Returns the source dict with all lines, or {}."""
    whole, start = {}, 1
    while start:
        text = invoke_tool("brain_read_source", {"source_id": source_id, "from_line": start})["result"]
        left, right = text.find("{"), text.rfind("}")
        if left < 0 or right < left:
            return {}
        try:
            page = json.loads(text[left:right + 1])
        except ValueError:
            return {}
        whole = {**page, "lines": whole.get("lines", []) + page["lines"]}
        start = page.get("next_line")
    return whole
