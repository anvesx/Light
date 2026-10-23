"""LiveListener: plain code that checks one call line against the brain. No model, no I/O."""
import re
from datetime import date

from control_plane.company_brain.topic_lexicon import topics_in

MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
CHANNELS = ("whatsapp", "sms", "email")
DATE_A = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(MONTHS) + r")[a-z]*\b")
DATE_B = re.compile(r"\b(" + "|".join(MONTHS) + r")[a-z]*\s+(\d{1,2})\b")
AMOUNT = re.compile(r"\b(\d+(?:\.\d+)?)\s*(lakhs?|crores?|cr|k)\b")
REVERSAL = ("no longer", "not needed", "nahi chahiye", "cancel", "drop it", "scrap")
NEGATIVE = ("unhappy", "worried", "frustrated", "high", "expensive", "concern", "risk")
OPEN_KINDS = ("requirement", "question", "blocker")
VIA = {"chat": "on WhatsApp", "email": "by email", "fathom": "in a call", "docx": "in a document", "live_call": "in a call"}


def values_in(text):
    """Pull out the comparable values of a text: channels, dates, amounts, reversal."""
    t = text.lower()
    found = {"channel": {c for c in CHANNELS if re.search(rf"\b{c}\b", t)}, "date": set(), "amount": set(), "reversal": set()}
    for d, m in DATE_A.findall(t):
        found["date"].add(f"{int(d)} {m}")
    for m, d in DATE_B.findall(t):
        found["date"].add(f"{int(d)} {m}")
    for n, unit in AMOUNT.findall(t):
        found["amount"].add(f"{float(n):g} {unit.rstrip('s')}")
    found["reversal"] = {cue for cue in REVERSAL if cue in t}
    return found


def nice_day(stamp):
    try:
        d = date.fromisoformat((stamp or "")[:10])
    except ValueError:
        return "an earlier day"
    return f"{d.strftime('%b')} {d.day}"


class LiveListener:
    def __init__(self, lexicon, checklist, open_items, active_decisions, translations=None, call_id="", total_lines=None):
        self.lexicon, self.translations = lexicon, translations or {}
        self.checklist = {c["topic"]: c for c in checklist}
        self.open_items = open_items
        self.decisions = active_decisions
        self.call_id, self.total = call_id, total_lines
        self.heard, self.asked, self.suggested = set(), set(), set()
        self.closing_done = False

    def clean_text(self, line):
        if line.get("clean_text"):
            return line["clean_text"]
        if line.get("lang", "en") == "en":
            return line["text"]
        return self.translations.get(f"{self.call_id}:{line['line_no']}") or line["text"]

    def hear(self, line):
        clean = self.clean_text(line)
        topics = topics_in(f"{line['text']} {clean}", self.lexicon)
        ours = str(line.get("speaker_id", "")).startswith("P")
        out = None
        if ours:
            if "?" in clean or "?" in line["text"]:
                self.asked.update(topics)
        else:
            out = self._on_client_line(line, clean, topics)
        self.heard.update(topics)
        if out is None and not self.closing_done and self._is_closing(line):
            out = self._closing(line)
        if out is None:
            return []
        self.suggested.add(out["topic"])
        return [out]

    def _on_client_line(self, line, clean, topics):
        topics = [t for t in topics if t not in self.suggested]
        for topic in topics:
            hit = self._contradiction(line, clean, topic)
            if hit:
                return hit
        for topic in topics:
            if topic not in self.asked and (topic in self.checklist or self._open_of(topic)):
                return self._gap(line, topic)
        for topic in topics:
            if self._concern_of(topic):
                return self._follow_up(line, topic)
        return None

    def _open_of(self, topic):
        return [i for i in self.open_items if i["topic"] == topic and i["kind"] in OPEN_KINDS]

    def _concern_of(self, topic):
        return [i for i in self.open_items if i["topic"] == topic and (i["kind"] == "risk" or (
            i["kind"] == "sentiment" and any(w in i["text"].lower() for w in NEGATIVE)))]

    def _label(self, topic):
        return self.lexicon.get("topics", {}).get(topic, {}).get("label", topic.replace("-", " "))

    @staticmethod
    def _cite(item):
        return {"item_id": item.get("item_id"), "source_id": item.get("source_id"), "origin_ref": item.get("origin_ref"),
                "line_no": item.get("line_from"), "quote": item.get("text")}

    def _make(self, line, kind, topic, text, why, cites):
        return {"line_no": line["line_no"], "kind": kind, "topic": topic, "text": text, "why": why, "cites": cites,
                "at_ms": int(line.get("t_sec", 0) * 1000)}

    def _contradiction(self, line, clean, topic):
        now = values_in(f"{line['text']} {clean}")
        for d in reversed([d for d in self.decisions if d["topic"] == topic]):
            then = values_in(d["text"])
            for cat in ("channel", "date", "amount"):
                new = now[cat] - then[cat]
                if then[cat] and now[cat] and new:
                    return self._said_differently(line, topic, d, ", ".join(sorted(new)))
            if now["reversal"] and not then["reversal"]:
                return self._said_differently(line, topic, d, "something different")
        return None

    def _said_differently(self, line, topic, decision, new):
        when, via = nice_day(decision.get("occurred_at")), VIA.get(decision.get("source_kind"), "")
        said = decision["text"].removeprefix("We decided: ").removeprefix("We decided:").strip()
        said = said[:1].lower() + said[1:]
        text = (f"On {when} {via} you agreed: {said} The client now says {new}. "
                f"Ask if the decision changes.").replace("  ", " ")
        why = f"Contradicts an active decision (source line {decision.get('line_from')})."
        return self._make(line, "contradiction", topic, text, why, [self._cite(decision)])

    def _gap(self, line, topic):
        item = self.checklist.get(topic)
        opens = self._open_of(topic)
        if item:
            text, why = item["question"], f"Kickoff checklist: {item.get('why') or 'learned from past deals'}"
            cites = [{"checklist_id": item.get("checklist_id"), "learned_from": item.get("learned_from", [])}]
        else:
            text = f"Ask about {self._label(topic).lower()}: {opens[-1]['text']}"
            why, cites = "Still open in the brain.", []
        cites += [self._cite(i) for i in opens[-2:]]
        return self._make(line, "gap", topic, text, why, cites)

    def _follow_up(self, line, topic):
        item = self._concern_of(topic)[-1]
        text = f"The client raised {self._label(topic).lower()} before: {item['text']} Ask what would settle it."
        return self._make(line, "follow_up", topic, text, "An earlier concern is still on record.", [self._cite(item)])

    def _is_closing(self, line):
        return bool(line.get("is_last")) or (bool(self.total) and line["line_no"] / self.total >= 0.85)

    def _closing(self, line):
        self.closing_done = True
        todo = [t for t in self.checklist if t not in self.heard and t not in self.asked and t not in self.suggested]
        if not todo:
            return None
        first = todo[0]
        rest = [self._label(t).lower() for t in todo[1:]]
        text = self.checklist[first]["question"] + (f" Also still unasked: {', '.join(rest)}." if rest else "")
        why = "The call is ending and this kickoff item was not raised."
        return self._make(line, "follow_up", first, text, why, [{"checklist_id": self.checklist[first].get("checklist_id"),
                                                                 "learned_from": self.checklist[first].get("learned_from", [])}])
