"""A small fixed brain for tests of later tickets: 4 sources, items with evidence, 2 deals, 2 playbooks, 3 checklist items."""

NAMES = {"C01": "Tailorbird Menswear", "C04": "MedBridge Clinics", "C07": "CareNest Clinics", "C08": "Zaika Foods",
         "C09": "Swasth Labs", "C10": "KiranaKart"}
SOURCES = (  # (origin_ref, area, kind, title, language, [(speaker, raw)])
    ("SAMPLE-1", "C04", "chat", "MedBridge WhatsApp", "hinglish",
     [("Dr Rao", "Patients ko reminders WhatsApp pe chahiye, SMS nahi."), ("Akbar Ali", "Theek hai, we will plan WhatsApp reminders."),
      ("Dr Rao", "Insurance claim upload bhi chahiye before launch.")]),
    ("SAMPLE-2", "C01", "email", "Tailorbird POS rollout", "en",
     [("Rhea Kulkarni", "Offline billing must work when the store internet drops."), ("Rhea Kulkarni", "GST invoice format is fixed by our CA.")]),
    ("SAMPLE-3", "C07", "fathom", "CareNest discovery call", "en",
     [("Anthony Fernandes", "Where will patient data be stored?"), ("Anil Rao", "It must stay in India. Also we want WhatsApp reminders.")]),
    ("SAMPLE-4", "C09", "fathom", "Swasth Labs follow-up", "en",
     [("Swasth CEO", "You never answered our data storage question."), ("Swasth CEO", "The price is too high for this plan.")]),
)
ITEMS = (  # (source ref, line, kind, topic, text)
    ("SAMPLE-1", 1, "requirement", "reminders", "Patients want reminders on WhatsApp, not SMS."),
    ("SAMPLE-1", 3, "requirement", "insurance-claims", "Insurance claim upload is needed before launch."),
    ("SAMPLE-2", 1, "requirement", "offline-mode", "Billing must work offline."),
    ("SAMPLE-3", 1, "question", "data-residency", "Where will patient data be stored?"),
    ("SAMPLE-3", 2, "requirement", "data-residency", "Patient data must stay in India."),
    ("SAMPLE-4", 1, "blocker", "data-residency", "The data storage question was never answered."),
)


def seed_sample(brain, data_conn):
    """Fill the brain once. Returns the ids: {"sources", "items", "deals", "playbooks", "checklist"}."""
    names = dict(NAMES)
    for r in data_conn.execute("SELECT client_id, name FROM clients"):
        names[r["client_id"]] = r["name"]
    for area in sorted({s[1] for s in SOURCES} | {"C08"}):
        brain.memory.ensure_area(area, name=names.get(area, area), kind="client")
    out = {"sources": {}, "items": {}, "deals": [], "playbooks": [], "checklist": []}
    for ref, area, kind, title, language, rows in SOURCES:
        lines = [{"line_no": n, "speaker": who, "text": text} for n, (who, text) in enumerate(rows, start=1)]
        out["sources"][ref] = brain.add_source(area, kind, title, "\n".join(r[1] for r in rows), origin_ref=ref,
                                               occurred_at="2026-10-01T10:00", participants=[], language=language, lines=lines)
    for ref, line, kind, topic, text in ITEMS:
        sid = out["sources"][ref]
        raw = brain.source_lines(sid)[line - 1]["text"]
        area = brain.get_source(sid)["area_id"]
        out["items"][f"{ref}:{line}"] = brain.add_brain_item(area, kind, text, topic=topic, source_id=sid, line_from=line, line_to=line,
                                                             quote_raw=raw, quote_clean=raw, confidence=0.9)
    brain.upsert_project(project_id="PR05", area_id="C04", name="Patient Booking App", status="active", csm_id="P05")
    brain.add_revenue("C04", "PR05", "2026-09", 900000)
    for deal_id, area, industry, stage, tags in (("L20", "C07", "healthcare", "closing", ["insurance-claims", "reminders", "data-residency"]),
                                                 ("L21", "C08", "restaurant chain", "proposal", ["inventory-sync", "offline-mode"])):
        brain.upsert_deal(deal_id=deal_id, area_id=area, name=names[area], industry=industry, stage=stage, owner_id="P03",
                          value_inr=2500000, tags=tags)
        out["deals"].append(deal_id)
    for area, deal_id, label, industry, outcome, tags in (
            ("C04", "L05", "A healthcare clinic network", "healthcare", "won", ["reminders", "insurance-claims", "language-support"]),
            ("C09", "L22", "A diagnostics lab", "diagnostics", "lost", ["data-residency", "pricing"])):
        out["playbooks"].append(brain.save_playbook(
            source_area_id=area, deal_id=deal_id, client_label=label, industry=industry, outcome=outcome, revenue_inr=9000000,
            sections={"went_right": ["Clear scope"], "went_wrong": ["Late answer on data storage"]}, tags=tags, run_id="sample"))
    for topic, question, why, industries in (
            ("data-residency", "Where must the data be stored?", "A lost deal never got an answer.", ["healthcare", "diagnostics"]),
            ("reminders", "Which channel for reminders: SMS or WhatsApp?", "A won deal added WhatsApp late.", ["healthcare"]),
            ("offline-mode", "Must billing work without internet?", "A retail rollout found this late.", [])):
        out["checklist"].append(brain.save_checklist_item(topic=topic, question=question, why=why, learned_from=["L05"], industries=industries))
    return out
