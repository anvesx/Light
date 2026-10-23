"""Topic lexicon: cue words per topic and language, matched as whole words in lower case."""
import json
import re
from pathlib import Path

LEXICON_PATH = Path(__file__).resolve().parents[2] / "company_data" / "brain_sources" / "topic_lexicon.json"
_cache = {}


def load_lexicon(path=None):
    """Read the lexicon file. A missing file gives an empty lexicon."""
    path = Path(path or LEXICON_PATH)
    if not path.exists():
        return {"topics": {}}
    key = (str(path), path.stat().st_mtime_ns)
    if key not in _cache:
        _cache.clear()
        _cache[key] = json.loads(path.read_text(encoding="utf-8"))
    return _cache[key]


def _has(text, cue):
    edge = r"[\wऀ-ॿ]"
    return re.search(rf"(?<!{edge}){re.escape(cue.lower())}(?!{edge})", text) is not None


def topics_in(text, lexicon=None):
    """Topics whose cue words (any language) appear as whole words in the text, in lexicon order."""
    lexicon = lexicon if lexicon is not None else load_lexicon()
    text = text.lower()
    found = []
    for topic, entry in lexicon.get("topics", {}).items():
        cues = [c for lang in ("en", "hinglish", "hi") for c in entry.get(lang, [])]
        if any(_has(text, cue) for cue in cues):
            found.append(topic)
    return found
