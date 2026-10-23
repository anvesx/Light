# Design adapted from dsh (MIT, (c) 2026 DeepSeek), commit 687f282e8625c6b8d11ff58211a90524be2e4317
"""Fold the old middle of a long conversation into one summary message so a run fits the model window."""
import json
import re
from dataclasses import asdict, dataclass

SUMMARY_OPEN = "<compacted-summary>"
SUMMARY_CLOSE = "</compacted-summary>"
PREAMBLE = ("This is an automatic summary of earlier messages, made to free space. "
            "Treat it as established background and continue the task from the messages that follow.")

INSTRUCTION = "\n".join([
    "Condense the conversation below into a checkpoint that lets another model continue with no loss.",
    "Use these sections, in order, with short bullets. Write (none) for an empty section:",
    "## Goal", "## Decisions", "## Open questions", "## Numbers and ids", "## Source quote ids", "## Next step",
    "Keep exact numbers, ids, names and source quote ids. Do not mention that you are summarising.",
    f"If a {SUMMARY_OPEN} block is already present it is an older checkpoint: merge it, do not copy it.",
])

_CUES = re.compile(r"\b(decid\w*|decision|agreed|approved|open question|todo|must|deadline)\b|\?\s*$", re.I)
_IDS = re.compile(r"\b(?:[A-Za-z]{1,4}-?\d+[A-Za-z0-9-]*)\b")
_NUMBERS = re.compile(r"(?:INR|Rs\.?|\$)?\s?\d[\d,]*(?:\.\d+)?%?")


@dataclass
class CompactionNote:
    """What one compaction did. The run log stores it."""
    before_tokens: int
    after_tokens: int
    folded_messages: int
    kept_recent: int

    def as_dict(self) -> dict:
        return asdict(self)


def estimate_tokens(messages) -> int:
    """About 4 characters per token. Cheap and stable, same rule as dsh's estimate."""
    return len(json.dumps(messages, default=str, sort_keys=True)) // 4


def compact_if_needed(messages, *, window_tokens, model_call, threshold=0.8, keep_recent=6, prefix_tokens=0):
    """Return (messages, CompactionNote | None).

    model_call(messages) -> str is the gateway call. prefix_tokens is the size of the system prompt and tools.
    """
    before = estimate_tokens(messages) + prefix_tokens
    if before < threshold * window_tokens:
        return messages, None
    cut = _safe_cut(messages, keep_recent)
    middle = messages[1:cut]
    if not middle:
        return messages, None
    summary = model_call([{"role": "user", "content": INSTRUCTION + "\n\n" + _transcript(middle)}])
    framed = f"{PREAMBLE}\n\n{SUMMARY_OPEN}\n{str(summary).strip()}\n\n{_kept_facts(middle)}\n{SUMMARY_CLOSE}"
    result = [messages[0], {"role": "user", "content": framed}, *messages[cut:]]
    after = estimate_tokens(result) + prefix_tokens
    if after >= before:
        return messages, None
    return result, CompactionNote(before, after, len(middle), len(messages) - cut)


def _safe_cut(messages, keep_recent) -> int:
    """First index of the kept tail. Moves earlier so a tool result keeps its assistant tool call."""
    i = max(len(messages) - keep_recent, 1)
    while i > 1 and messages[i].get("role") == "tool":
        i -= 1
    return i


def _text(message) -> str:
    calls = message.get("tool_calls") or []
    extra = " " + json.dumps(calls, default=str, sort_keys=True) if calls else ""
    return str(message.get("content", "")) + extra


def _transcript(middle) -> str:
    return "\n".join(f"[{m.get('role')}] {_text(m)}" for m in middle)


def _kept_facts(middle) -> str:
    """Code-made list of decision lines, ids and numbers, so they survive even if the model drops them."""
    lines, ids, numbers = [], [], []
    for m in middle:
        for line in _text(m).splitlines():
            if _CUES.search(line) and line.strip() not in lines:
                lines.append(line.strip())
        for tok in _IDS.findall(_text(m)):
            if tok not in ids:
                ids.append(tok)
        for tok in _NUMBERS.findall(_text(m)):
            tok = tok.strip()
            if tok and tok not in numbers:
                numbers.append(tok)
    return "\n".join(["## Kept verbatim (made by code)",
                      *[f"- {x[:300]}" for x in lines[:20]],
                      "ids: " + ", ".join(ids[:60]),
                      "numbers: " + ", ".join(numbers[:60])])
