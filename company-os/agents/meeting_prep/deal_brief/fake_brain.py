"""Deterministic stand-in for the model: turns the context into a brief using only the cites it was given."""
import json

from control_plane.company_brain.topic_lexicon import load_lexicon, topics_in
from contract.types import ModelReply

from .pack import CONTEXT_MARKER, RISK_KINDS


def _context(req) -> dict:
    prompt = next(m["content"] for m in reversed(req.messages) if m["role"] == "user")
    return json.loads(prompt.split(CONTEXT_MARKER, 1)[1])


def _label(topic):
    entry = load_lexicon()["topics"].get(topic) or {}
    return entry.get("label") or topic.replace("-", " ")


def _topic(entry):
    return entry.get("topic") or next(iter(topics_in(entry["text"])), None)


def _flag(items, text):
    return text if all(i["confirmed"] for i in items) else f"Unconfirmed: {text}"


def _answer(c) -> dict:
    own = {}
    for i in c["items"]:
        own.setdefault(i["topic"], []).append(i)
    ideas, seen = [], set()
    for pb in c["similar"]:
        for section, verb in (("went_wrong", "Deal with early"), ("went_right", "Offer")):
            for e in pb["sections"][section]:
                topic = _topic(e)
                if (topic, section) in seen:
                    continue
                seen.add((topic, section))
                mine = own.get(topic, [])
                text = f"{verb} {_label(topic)}: {e['text']}" if topic else f"{verb}: {e['text']}"
                text = _flag(mine, text) if mine else text
                ideas.append({"text": text, "topic": topic, "cites": [pb["playbook_id"]] + [i["item_id"] for i in mine],
                              "because": f"{pb['client_label']} ({pb['outcome']}): {e['text']}"})
    for topic in c["objection_topics"]:  # an objection the playbooks did not cover still gets an idea
        mine = own.get(topic, [])
        if mine and not any(i["topic"] == topic for i in ideas):
            ideas.append({"text": _flag(mine, f"Settle {_label(topic)} before the next call"), "topic": topic,
                          "cites": [i["item_id"] for i in mine], "because": f"This deal raised it: {mine[0]['text']}"})
    risks = [{"text": _flag([i], f"{_label(i['topic'])}: {i['text']}"), "cites": [i["item_id"]]}
             for i in c["items"] if i["kind"] in RISK_KINDS and i["topic"]]
    for pb in c["similar"]:
        for e in pb["sections"]["went_wrong"]:
            risks.append({"text": f"{pb['client_label']} ({pb['outcome']}) went wrong on: {e['text']}", "cites": [pb["playbook_id"]]})
    questions, asked = [], set()
    for k in c["checklist"]:
        asked.add(k["topic"])
        questions.append({"topic": k["topic"], "question": k["question"], "why": k["why"], "cites": k["playbook_ids"]})
    for pb in c["similar"]:  # what past clients changed later, even when the checklist lacks it
        for e in pb["sections"]["later_changed_to"]:
            topic = _topic(e)
            if topic and topic not in asked:
                asked.add(topic)
                questions.append({"topic": topic, "question": f"Is {_label(topic)} needed? Ask it now, not later.",
                                  "why": f"{pb['client_label']} changed this late: {e['text']}", "cites": [pb["playbook_id"]]})
    names = ", ".join(p["client_label"] for p in c["similar"]) or "no similar client"
    summary = (f"{c['deal']['name']}: {len(c['similar'])} similar past client(s) ({names}), {len(ideas)} idea(s), "
               f"{len(risks)} risk(s), {len(questions)} kickoff question(s).")
    return {"deal_id": c["deal"]["deal_id"], "similar": [{k: p.get(k) for k in ("playbook_id", "client_label", "outcome", "score", "why")}
                                                          for p in c["similar"]],
            "closing_ideas": ideas, "risks": risks, "kickoff_questions": questions, "summary": summary}


def brain(request) -> ModelReply:
    return ModelReply(text=json.dumps(_answer(_context(request))))
