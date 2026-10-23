"""Playbook rules: code builds the redacted sections, tags and kickoff checklist of one closed deal. The model only words them."""
import re

from .redaction import redact
from .retrieval import _group
from .topic_lexicon import load_lexicon, topics_in

SECTIONS = ("initially_wanted", "later_changed_to", "chose", "went_right", "went_wrong")
NEGATIVE = re.compile(r"\b(?:unhappy|shocked|worried|frustrated|too much|too high|too long|expensive)\b", re.I)
OBJECTION_TOPICS = ("pricing", "timeline")  # these are handled as objections, not as kickoff questions
PREFIX = re.compile(r"^(?:what went right|what changed late|what went wrong)\s*:\s*", re.I)
QUESTIONS = {
    "insurance-claims": "Will users need to upload insurance claims, and who checks them?",
    "reminders": "Which channel for reminders: SMS or WhatsApp?",
    "language-support": "Which languages must the screens support, for example Hindi?",
    "data-residency": "Where must the data be stored?",
    "gift-vouchers": "Must staff check a gift voucher balance at billing?",
    "offline-mode": "Must billing work when the internet drops?",
    "gst-invoicing": "Which GST invoice format is fixed by the client's accountant?",
    "phased-mvp": "Would the client prefer a small first release before the full plan?",
    "launch-date": "Is there a fixed launch date, and what depends on it?",
    "reporting": "Which reports or dashboards does the client need, and how often?",
    "lab-integration": "Which lab or external systems must the app connect to?",
    "training": "Who needs training before go-live?",
    "compliance": "Is a privacy or compliance review needed before launch?",
}


def _label(topic):
    return load_lexicon().get("topics", {}).get(topic, {}).get("label", topic.replace("-", " ").capitalize())


def _entry(items, redactor):
    newest = items[-1]
    text = PREFIX.sub("", newest["text"])
    return {"text": redactor(text), "topic": newest["topic"], "item_ids": [i["item_id"] for i in items]}


def _by_topic(items):
    out = {}
    for i in sorted(items, key=lambda i: (i["when"], i["item_id"])):
        if i["topic"]:
            out.setdefault(i["topic"], []).append(i)
    return out


def build(data, data_conn):
    """Return {"client_label", "revenue_inr", "sections", "tags", "checklist"} for the deal in `data` (see brain_read_deal)."""
    redactor = lambda t: redact(t, data_conn)
    deal, items = data["deal"], [i for i in data["items"]]
    won = deal["stage"] == "won"
    closing = (data.get("won_on") if won else data.get("last_call")) or max((i["when"] for i in items), default="")
    kickoff = (data.get("project") or {}).get("start_on") or closing
    sections = {s: [] for s in SECTIONS}
    before = [i for i in items if i["kind"] == "requirement" and i["when"] <= closing]
    sections["initially_wanted"] = [_entry(v[:1], redactor) for v in _by_topic(before).values()]
    if won:
        late = [i for i in items if i["kind"] in ("requirement", "decision") and i["when"] >= kickoff and i["when"] > closing]
        sections["later_changed_to"] = [_entry(v, redactor) for v in _by_topic(late).values()]
    decisions = [i for i in items if i["kind"] == "decision" and i["state"] != "superseded"]
    sections["chose"] = [_entry(v, redactor) for v in _by_topic(decisions).values()]
    by_topic = _by_topic(items)
    if won:
        for topic, rows in by_topic.items():
            later = [i for i in rows if i["when"] > closing]
            if any(i["when"] <= closing for i in rows) and later and all(i["kind"] == "fact" for i in later):
                sections["went_right"].append(_entry(later, redactor))
    else:
        bad = [i for i in items if i["kind"] in ("blocker", "risk") or (i["kind"] == "sentiment" and NEGATIVE.search(i["text"]))]
        wrong = _by_topic(bad)
        for topic in topics_in(data.get("lost_reason") or ""):
            if topic not in wrong and by_topic.get(topic):
                wrong[topic] = by_topic[topic]
        sections["went_wrong"] = [_entry(v, redactor) for v in wrong.values()]
    tags = sorted({e["topic"] for entries in sections.values() for e in entries if e["topic"]})
    industry = deal["industry"] or "business"
    checklist = []
    for section, why in (("later_changed_to", f"A past {industry} project added this late."),
                         ("went_wrong", f"A lost {industry} deal went wrong on this.")):
        for e in sections[section]:
            if e["topic"] not in OBJECTION_TOPICS:
                checklist.append({"topic": e["topic"], "question": QUESTIONS.get(e["topic"], f"What does the client need for {_label(e['topic']).lower()}?"),
                                  "why": why, "learned_from": [deal["deal_id"]], "industries": sorted(_group(industry) or {industry})})
    return {"client_label": f"A {industry} client", "revenue_inr": data.get("revenue_inr") or 0, "sections": sections,
            "tags": tags, "checklist": checklist}


def texts_of(plan):
    """Every string that will reach the library, for the leak check."""
    out = [plan["client_label"]]
    for entries in plan["sections"].values():
        out += [e["text"] for e in entries]
    for c in plan.get("checklist", []):
        out += [c["question"], c["why"]]
    return out
