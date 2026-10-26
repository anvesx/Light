"""Stand-in library for the exam while the Playbook writer's real output is not in the brain: built from the answer keys."""
from control_plane.company_brain.topic_lexicon import load_lexicon

STAGE = {"negotiation": "closing", "proposal": "proposal"}
OWN_ITEMS = {  # (kind, topic, text, confidence) said by the prospect, per live deal
    "L20": (("question", "data-residency", "Where will patient data be stored?", 0.9),
            ("risk", "pricing", "The price looks high for a clinic chain.", 0.9),
            ("requirement", "reminders", "Patients may want reminders in their language.", 0.4)),
    "L21": (("risk", "timeline", "They want to open the first outlets within two months.", 0.9),
            ("requirement", "inventory-sync", "Stock should sync across outlets.", 0.9))}


def _label(topic):
    return (load_lexicon()["topics"].get(topic) or {}).get("label") or topic.replace("-", " ")


def seed_exam_library(brain, data_conn, key):
    """Seed live deals with their own items, past playbooks and a kickoff checklist. Returns the checklist topics."""
    clients = {r["client_id"]: dict(r) for r in data_conn.execute("SELECT client_id, name, industry FROM clients")}
    leads = {r["lead_id"]: dict(r) for r in data_conn.execute("SELECT lead_id, stage, value_inr, owner_id FROM leads")}
    for deal in key["deals"]:
        area, lead = deal["area_id"], leads[deal["deal_id"]]
        items = OWN_ITEMS[deal["deal_id"]]
        raw = [t for _, _, t, _ in items]
        sid = brain.add_source(area, "fathom", f"{clients[area]['name']} call", "\n".join(raw), origin_ref=f"EXAM-{deal['deal_id']}",
                               occurred_at="2026-10-01T10:00", participants=[], language="en",
                               lines=[{"line_no": n, "speaker": "Prospect", "text": t} for n, t in enumerate(raw, 1)])
        for n, (kind, topic, text, conf) in enumerate(items, 1):
            brain.add_brain_item(area, kind, text, topic=topic, source_id=sid, line_from=n, line_to=n, quote_raw=text,
                                 quote_clean=text, confidence=conf, deal_id=deal["deal_id"])
        brain.upsert_deal(deal_id=deal["deal_id"], area_id=area, name=clients[area]["name"], industry=clients[area]["industry"],
                          stage=STAGE[lead["stage"]], owner_id=lead["owner_id"], value_inr=lead["value_inr"],
                          tags=sorted({i[1] for i in items}))
    learned = {}
    for pb in key["playbooks"]:
        area = pb["area_id"]
        sections = {"later_changed_to": [{"text": f"Asked for {_label(t)} after the project began", "topic": t} for t in pb["later_changed_topics"]],
                    "went_right": [{"text": f"{_label(t)} helped the client trust the plan", "topic": t} for t in pb["went_right_topics"]],
                    "went_wrong": [{"text": f"{_label(t)} was not handled in time", "topic": t} for t in pb["went_wrong_topics"]]}
        tags = sorted({t for s in sections.values() for e in s for t in [e["topic"]]})
        brain.save_playbook(source_area_id=area, deal_id=pb["deal_id"], client_label=f"A {clients[area]['industry']} client",
                            industry=clients[area]["industry"], outcome=pb["outcome"], revenue_inr=0, sections=sections, tags=tags,
                            run_id="exam-fixture")
        for t in pb["later_changed_topics"] + pb["went_wrong_topics"]:
            learned.setdefault(t, []).append(pb["deal_id"])
    for topic, deals in sorted(learned.items()):
        brain.save_checklist_item(topic=topic, question=f"Do you need {_label(topic).lower()}? Tell us now.",
                                  why="Past clients raised it late or it cost a deal.", learned_from=deals, industries=[])
    return sorted(learned)
