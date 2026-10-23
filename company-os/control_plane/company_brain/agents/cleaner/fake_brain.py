"""Deterministic stand-in for the Cleaner's model: looks each line up in the translations fixture."""
import json
import re
from pathlib import Path

from control_plane.company_brain.language import detect_language
from contract.types import ModelReply

from .pack import CONTEXT_MARKER

TRANSLATIONS = Path(__file__).resolve().parents[4] / "company_data" / "brain_sources" / "translations.json"


ENGLISH_WORDS = frozenset("the is are we you it i will can that this have do in on not and a of for to be with so but hi thanks only up me let shall".split())


def looks_english(text):
    words = re.findall(r"[a-z']+", text.lower())
    return detect_language(text) == "en" and any(w in ENGLISH_WORDS for w in words)


def _context(req):
    prompt = next(m["content"] for m in reversed(req.messages) if m["role"] == "user")
    return json.loads(prompt.split(CONTEXT_MARKER, 1)[1])


def brain(request) -> ModelReply:
    context = _context(request)
    table = json.loads(TRANSLATIONS.read_text(encoding="utf-8")) if TRANSLATIONS.exists() else {}
    rows = []
    for l in context["to_translate"]:
        text = table.get(f"{context['origin_ref']}:{l['line_no']}")
        rows.append({"line_no": l["line_no"], "clean_text": text or (l["text"] if looks_english(l["text"]) else None)})
    return ModelReply(text=json.dumps({"translations": rows}))
