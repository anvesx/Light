"""Record sync: copy company records (clients, projects, leads, invoices, SOW changes) into the brain. Safe to run twice."""
from .topic_lexicon import topics_in

STAGE_OF_LEAD = {"new": "discovery", "qualified": "discovery", "proposal": "proposal", "negotiation": "closing",
                 "won": "won", "lost": "lost"}


def sync_records(data_conn, brain, until=None) -> dict:
    """Areas, projects, deals (from leads), revenue (from invoices) and accepted SOW changes as requirement items."""
    day = (until or "9999-12-31")[:10]
    counts = {"areas": 0, "projects": 0, "deals": 0, "revenue": 0, "items_added": 0}
    clients = {r["client_id"]: dict(r) for r in data_conn.execute("SELECT * FROM clients ORDER BY client_id")}
    for cid, c in clients.items():
        brain.memory.ensure_area(cid, name=c["name"], kind="client")
        counts["areas"] += 1
    for p in data_conn.execute("SELECT * FROM projects ORDER BY project_id"):
        brain.upsert_project(project_id=p["project_id"], area_id=p["client_id"], name=p["name"], status=p["status"],
                             csm_id=p["csm_id"], start_on=p["start_on"], planned_end_on=p["planned_end_on"])
        counts["projects"] += 1
    kept = {d["deal_id"]: d["tags"] for d in brain.deals(list(clients))}
    for lead in data_conn.execute("SELECT * FROM leads WHERE client_id IS NOT NULL AND created_on <= ? ORDER BY lead_id", (day,)):
        c = clients.get(lead["client_id"])
        if c is None:
            continue
        brain.upsert_deal(deal_id=lead["lead_id"], area_id=lead["client_id"], name=c["name"], industry=c["industry"],
                          stage=STAGE_OF_LEAD[lead["stage"]], owner_id=lead["owner_id"], value_inr=lead["value_inr"],
                          tags=kept.get(lead["lead_id"], []))
        counts["deals"] += 1
    for inv in data_conn.execute("SELECT * FROM client_invoices WHERE month <= ? ORDER BY invoice_id", (day[:7],)):
        if inv["project_id"] and inv["client_id"] in clients:
            brain.add_revenue(inv["client_id"], inv["project_id"], inv["month"], inv["amount_inr"])
            counts["revenue"] += 1
    counts["items_added"] = _sync_sow_changes(data_conn, brain, day)
    return counts


def _sync_sow_changes(data_conn, brain, day):
    added = 0
    sql = ("SELECT c.*, s.client_id, s.project_id FROM sow_changes c JOIN sows s USING (sow_id)"
           " WHERE c.accepted = 1 AND c.date <= ? ORDER BY c.date, c.change_id")
    for ch in data_conn.execute(sql, (day,)):
        ref = f"record:{ch['change_id']}"
        if brain.source_by_ref(ref) is not None or not ch["client_id"]:
            continue
        text = ch["change_text"]
        source_id = brain.add_source(
            ch["client_id"], "record", f"SOW change {ch['change_id']}", text, origin_ref=ref, occurred_at=ch["date"] + "T09:00",
            participants=[], language="en", lines=[{"line_no": 1, "speaker": "SOW record", "text": text}],
            project_id=ch["project_id"], received_at=ch["date"] + "T09:00")
        brain.set_clean_lines(source_id, [{"line_no": 1, "clean_text": text, "speaker": "SOW record"}])
        topics = topics_in(text)
        brain.add_brain_item(ch["client_id"], "requirement", text, topic=topics[0] if topics else None, source_id=source_id,
                             line_from=1, line_to=1, quote_raw=text, quote_clean=text, confidence=1.0,
                             project_id=ch["project_id"], said_at=ch["date"] + "T09:00")
        brain.set_source_status(source_id, "linked")
        added += 1
    return added
