"""Deterministic stand-in for the Extractor's model: the same cue rules the code uses to find candidates."""
import json

from contract.types import ModelReply

from ...extract_rules import propose_items
from .pack import CONTEXT_MARKER


def brain(request) -> ModelReply:
    prompt = next(m["content"] for m in reversed(request.messages) if m["role"] == "user")
    context = json.loads(prompt.split(CONTEXT_MARKER, 1)[1])
    return ModelReply(text=json.dumps({"items": propose_items(context["candidate_lines"])}, ensure_ascii=False))
