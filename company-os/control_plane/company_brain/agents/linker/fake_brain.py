"""Deterministic stand-in for the model: it confirms the links the rules planned and leaves unsure pairs out."""
import json

from contract.types import ModelReply

from .pack import CONTEXT_MARKER


def brain(request) -> ModelReply:
    prompt = next(m["content"] for m in reversed(request.messages) if m["role"] == "user")
    context = json.loads(prompt.split(CONTEXT_MARKER, 1)[1])
    return ModelReply(text=json.dumps({"links": context["links"], "scope": context["scope"]}))
