"""Finds and masks passwords, keys and tokens in text. Used by the tools, the check step and memory."""
import re

MASK = "[secret removed]"
_LABEL = (r"(?:pw|pwd|passwd|password|passcode|pass\s?phrase|secret|token|api[ _-]?key|apikey|access[ _-]?key|"
          r"private[ _-]?key|keys?)")
# label, then ":" or "=" (strong) or "is" / "was" (weak), then the value
_PAIR = re.compile(rf"\b({_LABEL})\b(\s*(?:[:=]|\b(?:is|are|was|were)\b)\s*)([^\s,;]+)", re.I)
_TOKEN_LIKE = [re.compile(p) for p in (
    r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{8,}", r"\bAKIA[0-9A-Z]{16}\b", r"\bgh[pousr]_[A-Za-z0-9]{20,}",
    r"\bxox[abprs]-[A-Za-z0-9-]{10,}", r"\bshp(?:at|ss|ca)_[A-Za-z0-9]{16,}",
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"\b(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{24,}\b")]
_NOT_A_VALUE = {"in", "on", "at", "the", "a", "an", "shared", "stored", "sent", "ready", "attached", "here", "now",
                "vault", "below", "above", "done", "added", "uploaded", "not", "never", "with", "via", "to", "only",
                "will", "can", "please", "safe", "secure", "ok", "this", "that", "it", "no", "yes", "given", "set"}
_ASK_WORD = re.compile(r"\b(?:password|passcode|passwd|pwd|pw|credentials?)\b", re.I)
_ASK_VERB = re.compile(r"\b(?:send|shar|giv|provid|past|typ|tell|email|enter|post|supply|need|reply with)\w*", re.I)
_NEGATION = re.compile(r"\b(?:never|not|don't|dont|do not|without|avoid|instead of|no)\b", re.I)


def _value_is_secret(value, strong):
    value = value.strip("\"'`()[]<>").rstrip(".!?")
    if value.lower() in _NOT_A_VALUE:
        return None
    if strong:
        return value if len(value) >= 4 else None
    has_mark = any(ch.isdigit() for ch in value) or any(ch in "-_!@#$%^&*" for ch in value)
    return value if len(value) >= 6 and has_mark else None


def _spans(text):
    """(start, end) of each secret value found in text."""
    found = []
    for m in _PAIR.finditer(text or ""):
        strong = m.group(2).strip().lower() not in ("is", "are", "was", "were")
        value = _value_is_secret(m.group(3), strong)
        if value:
            start = m.start(3) + m.group(3).find(value)
            found.append((start, start + len(value)))
    for rx in _TOKEN_LIKE:
        found += [m.span() for m in rx.finditer(text or "")]
    return sorted(found)


def find_secrets(text) -> list:
    return [text[a:b] for a, b in _spans(text)]


def has_secret(text) -> bool:
    return bool(_spans(text if isinstance(text, str) else ""))


def mask(text):
    """Replace every secret value with a marker. Non-text values pass through."""
    if not isinstance(text, str):
        return text
    out, last = [], 0
    for a, b in _spans(text):
        if a < last:
            continue
        out += [text[last:a], MASK]
        last = b
    return "".join(out) + text[last:]


def mask_all(value):
    """Mask every string inside a dict, list or tuple."""
    if isinstance(value, str):
        return mask(value)
    if isinstance(value, dict):
        return {k: mask_all(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [mask_all(v) for v in value]
    return value


def asks_for_password(text) -> bool:
    """True if a sentence asks the reader to send a password. A sentence that says never or do not is fine."""
    for sentence in re.split(r"[.!?\n]+", text or ""):
        if _ASK_WORD.search(sentence) and _ASK_VERB.search(sentence) and not _NEGATION.search(sentence):
            return True
    return False
