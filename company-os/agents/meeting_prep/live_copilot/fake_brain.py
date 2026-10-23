"""Deterministic stand-in for the model: writes the end-of-call summary from the context."""
import json

from contract.types import ModelReply

from .pack import CONTEXT_MARKER


def _context(req) -> dict:
    prompt = next(m["content"] for m in reversed(req.messages) if m["role"] == "user")
    return json.loads(prompt.split(CONTEXT_MARKER, 1)[1])


def _answer(context) -> dict:
    sug = context["suggestions"]
    topics = sorted({s["topic"].replace("-", " ") for s in sug})
    summary = (f"Call: {context['title']}. {len(context['transcript'])} lines. "
               + (f"The copilot suggested {len(sug)} question(s) on: {', '.join(topics)}." if sug else "No question was suggested."))
    steps = [f"Follow up on {s['topic'].replace('-', ' ')} (line {s['line_no']})." for s in sug]
    return {"summary": summary, "next_steps": steps}


def brain(request) -> ModelReply:
    return ModelReply(text=json.dumps(_answer(_context(request))))
