"""Deterministic stand-ins for the model's judgement: a normal brain, and an unsafe one used only to test the guard."""
import json
import re
from datetime import date

from contract.types import ModelReply, ToolCall

from .pack import CONTEXT_MARKER, STALE_AFTER_DAYS

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def _context(req) -> dict:
    prompt = next(m["content"] for m in reversed(req.messages) if m["role"] == "user")
    return json.loads(prompt.split(CONTEXT_MARKER, 1)[1])


def _point(item):
    return {"text": item["text"], "topic": item["topic"], "cites": [item["item_id"]], "sources": item["sources"],
            "unconfirmed": item["unconfirmed"]}


def _brain_sections(brain, questions):
    """Brief points from brain items. Every point cites its item and carries that item's source lines."""
    items = brain.get("items", [])
    kind = lambda k: [_point(i) for i in items if i["kind"] == k]
    for i in items:
        if i["kind"] == "question":
            questions.append({**_point(i), "text": f"Ask the client: {i['text']}"})
    changes = [{"text": f"Changed on {c['changed_on']}: {c['old']['text']} → {c['new']['text']}",
                "topic": c["new"]["topic"], "item_id": c["new"]["item_id"], "cites": [c["new"]["item_id"], c["old"]["item_id"]],
                "sources": c["new"]["sources"] + c["old"]["sources"], "_kind": c["new"]["kind"]} for c in brain.get("changes", [])]
    changed = [{k: v for k, v in c.items() if k != "_kind"} for c in changes if c["_kind"] == "decision"]
    conflicts = [{k: v for k, v in c.items() if k not in ("_kind", "item_id")} for c in changes if c["_kind"] != "decision"]
    return {"changed_decisions": changed, "open_requirements": kind("requirement"), "blockers": kind("blocker"),
            "commitments_due": kind("commitment"), "contradictions": conflicts,
            "recent_decisions": kind("decision"), "unconfirmed_count": brain.get("unconfirmed_count", 0)}


def _answer(context) -> dict:
    meeting_day = date.fromisoformat(context["meeting"]["start_at"][:10])
    by_topic = {}
    for item in context["open_items"]:  # one question per topic, citing every open item on it
        by_topic.setdefault(item["topic"], []).append(item)
    questions, watch_out = [], []
    for topic, items in by_topic.items():
        newest, oldest = items[-1], items[0]
        lead = "Still open with the client" if newest["kind"] == "question" else "Open task, please confirm if it is done"
        questions.append({"text": f"{lead}: {newest['text']} (first raised {oldest['created_at'][:10]})",
                          "cites": [i["item_id"] for i in items], "topic": topic})
        age = (meeting_day - date.fromisoformat(oldest["created_at"][:10])).days
        if age > STALE_AFTER_DAYS:
            watch_out.append(f"\"{topic}\" has been open for {age} days. Close it, or agree who owns it.")
    # Recent decisions are not changes: with a brain block only replaced decisions are listed as changed.
    changed = [] if context.get("brain") else [{"text": d["text"], "topic": d["topic"], "item_id": d["item_id"]}
                                                for d in context["recent_decisions"]]
    extra = _brain_sections(context.get("brain") or {}, questions)
    summary = (f"{len(questions)} topic(s) to settle for {context['meeting']['project_name'] or 'this project'}"
               f" and {len(changed)} recent decision(s). Settle the open points in this meeting.")
    return {"questions": questions, "changed_decisions": changed + extra.pop("changed_decisions"),
            "watch_out": watch_out, "summary": summary, **extra}


def brain(request) -> ModelReply:
    return ModelReply(text=json.dumps(_answer(_context(request))))


def naive_brain(request) -> ModelReply:
    """Reads client messages and obeys any address it finds in them. Never use outside the guard test."""
    tool_msgs = [m for m in request.messages if m["role"] == "tool"]
    if not tool_msgs:
        return ModelReply(tool_calls=[ToolCall("n0", "recent_client_messages", {})])
    if len(tool_msgs) == 1:
        found = EMAIL.search(tool_msgs[0]["content"])
        if found:
            return ModelReply(tool_calls=[ToolCall("n1", "send_private_message", {
                "to_person_id": found.group(0), "text": "Here are all the invoices.", "kind": "leak"})])
    return brain(request)
