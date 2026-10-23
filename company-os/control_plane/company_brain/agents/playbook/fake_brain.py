"""Deterministic stand-in for the model: it returns the playbook the rules built. A leaky brain is for the check-step test only."""
import json

from contract.types import ModelReply

from .pack import CONTEXT_MARKER


def _context(request):
    prompt = next(m["content"] for m in reversed(request.messages) if m["role"] == "user")
    return json.loads(prompt.split(CONTEXT_MARKER, 1)[1])


def brain(request) -> ModelReply:
    c = _context(request)
    keep = ("client_label", "revenue_inr", "sections", "tags", "checklist")
    return ModelReply(text=json.dumps({k: c[k] for k in keep}))


def leaky_brain(request) -> ModelReply:
    """Adds a client contact name, an email and a phone number to the first entry. The check step must refuse."""
    c = _context(request)
    out = {k: c[k] for k in ("client_label", "revenue_inr", "sections", "tags", "checklist")}
    entry = next(e for entries in out["sections"].values() for e in entries)
    entry["text"] += " Ask Nandini Sethi on nandini.sethi@medbridge-clinics.example or 98200 12345."
    return ModelReply(text=json.dumps(out))
