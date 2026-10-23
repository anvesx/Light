"""Plain-code rules for the Cleaner and Extractor: filler removal, speaker names, kind and topic cues, safety checks."""
import json
import re
from pathlib import Path

from control_plane.guardrails.outside_text import looks_like_instruction

from .brain_store import ITEM_KINDS
from .language import detect_language
from .topic_lexicon import load_lexicon, topics_in

CUES_PATH = Path(__file__).resolve().parents[2] / "company_data" / "brain_sources" / "kind_cues.json"
KIND_ORDER = ("decision", "requirement", "blocker", "commitment", "risk", "sentiment", "money", "question")
FILLER = re.compile(r"(?:(?<=\s)|^)(?:u+m+|u+h+|er+m*|you know)\b[,.]?\s*", re.I)
OPINION = re.compile(r"\b(lazy|incompetent|useless|unprofessional|careless|sloppy|underperform\w*|"
                     r"poor (?:work|performance)|not capable)\b", re.I)
CONFIDENT, SEVERAL_TOPICS, UNTRANSLATED = 0.9, 0.85, 0.5
MONEY = re.compile(r"(?:inr|rs\.?|₹)\s?[\d,.]+(?:\s?(?:lakh|crore|k))?|\b\d+(?:\.\d+)?\s?(?:lakh|crore)\b", re.I)


def load_kind_cues(path=None):
    return json.loads(Path(path or CUES_PATH).read_text(encoding="utf-8"))


def remove_filler(text):
    """Drop um, uh and "you know" from an English line; keep everything else."""
    return re.sub(r"\s{2,}", " ", FILLER.sub("", text)).strip() or text.strip()


def needs_translation(text):
    return detect_language(text) != "en"


def fix_speaker(raw, participants):
    """Match a raw speaker label to a participant's full name (exact, then first name). Else keep the raw label."""
    label = (raw or "").strip()
    key = label.lower()
    if not key:
        return label
    names = [p.get("name") or "" for p in participants]
    for name in names:
        if name.lower() == key:
            return name
    first = key.split()[0]
    hits = [n for n in names if n and n.lower().split()[0] == first]
    return hits[0] if len(hits) == 1 else label


def is_injection(text):
    return looks_like_instruction(text or "")


def kind_of(text, cues=None):
    cues = cues or load_kind_cues()
    low = text.lower()
    for kind in KIND_ORDER:
        if any(c in low for c in cues.get(kind, [])):
            return kind
    return "fact"


def value_of(kind, text):
    if kind != "money":
        return None
    found = MONEY.search(text)
    return found.group(0).strip() if found else None


def has_opinion(text):
    """True when the text judges a person's work. The brain stores no such opinion."""
    return OPINION.search(text or "") is not None


def propose_items(lines, lexicon=None, cues=None):
    """Candidate items from clean lines: [{kind, topic, text, line_from, line_to, confidence, value}].

    A line is a candidate when it has a topic cue. Lines that look like orders are skipped. A line the Cleaner could
    not translate keeps its raw text, gets low confidence and is still proposed.
    """
    lexicon, cues = lexicon or load_lexicon(), cues or load_kind_cues()
    out = []
    for line in lines:
        text = line.get("clean_text") or line.get("text") or ""
        if not text.strip() or is_injection(text) or has_opinion(text):
            continue
        topics = topics_in(text, lexicon)
        if not topics:
            continue
        kind = kind_of(text, cues)
        if line.get("untranslated"):
            confidence = UNTRANSLATED
        else:
            confidence = CONFIDENT if len(topics) == 1 else SEVERAL_TOPICS
        out.append({"kind": kind, "topic": topics[0], "text": text.strip(), "line_from": line["line_no"],
                    "line_to": line["line_no"], "confidence": confidence, "value": value_of(kind, text)})
    return out


def item_problems(item, clean_by_line, lexicon=None, skip_lines=()):
    """Plain-language problems with one proposed item. An empty list means it passes the check step."""
    lexicon = lexicon or load_lexicon()
    problems = []
    start, end = item.get("line_from"), item.get("line_to")
    if not isinstance(start, int) or not isinstance(end, int) or start > end or any(n not in clean_by_line for n in range(start, end + 1)):
        return [f"lines {start}-{end} do not exist in the source"]
    quote = " ".join(clean_by_line[n] for n in range(start, end + 1))
    if not str(item.get("text", "")).strip() or str(item["text"]).strip().lower() not in quote.lower():
        problems.append(f"the text of lines {start}-{end} is not a quote of the clean text")
    if item.get("topic") not in lexicon.get("topics", {}):
        problems.append(f"topic {item.get('topic')!r} is not in the topic lexicon")
    if item.get("kind") not in ITEM_KINDS:
        problems.append(f"kind {item.get('kind')!r} is not allowed")
    if not isinstance(item.get("confidence"), (int, float)) or not 0 <= item["confidence"] <= 1:
        problems.append("confidence must be a number from 0 to 1")
    if has_opinion(str(item.get("text", ""))):
        problems.append("an opinion about a person's work is not stored")
    if any(n in skip_lines for n in range(start, end + 1)):
        problems.append(f"line {start} is an outside instruction, not a fact")
    return problems
