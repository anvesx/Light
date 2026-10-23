-- Company brain tables. They share the company memory file. Safe to run many times.
-- Items live in the memory `items` table; brain_item_facts and brain_evidence add the brain fields.
CREATE TABLE IF NOT EXISTS brain_sources (
    source_id TEXT PRIMARY KEY,
    area_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT,
    raw_text TEXT NOT NULL,
    origin_ref TEXT,
    occurred_at TEXT,
    received_at TEXT NOT NULL,
    participants TEXT NOT NULL DEFAULT '[]',
    language TEXT,
    project_id TEXT,
    deal_id TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    submitted_by TEXT
);
CREATE INDEX IF NOT EXISTS brain_sources_by_area ON brain_sources(area_id, received_at);
CREATE INDEX IF NOT EXISTS brain_sources_by_ref ON brain_sources(origin_ref);
-- Raw text is never changed after the source is stored.
CREATE TRIGGER IF NOT EXISTS brain_sources_raw_fixed BEFORE UPDATE OF raw_text ON brain_sources
WHEN NEW.raw_text IS NOT OLD.raw_text
BEGIN SELECT RAISE(ABORT, 'raw source text never changes'); END;

CREATE TABLE IF NOT EXISTS brain_source_lines (
    source_id TEXT NOT NULL,
    line_no INTEGER NOT NULL,
    raw_speaker TEXT,
    raw_text TEXT NOT NULL,
    t_sec REAL,
    lang TEXT,
    clean_speaker TEXT,
    clean_text TEXT,
    PRIMARY KEY (source_id, line_no)
);
CREATE TRIGGER IF NOT EXISTS brain_lines_raw_fixed BEFORE UPDATE OF raw_text, raw_speaker ON brain_source_lines
WHEN NEW.raw_text IS NOT OLD.raw_text OR NEW.raw_speaker IS NOT OLD.raw_speaker
BEGIN SELECT RAISE(ABORT, 'raw source lines never change'); END;

CREATE TABLE IF NOT EXISTS brain_item_facts (
    item_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    project_id TEXT,
    deal_id TEXT,
    speaker_id TEXT,
    said_at TEXT,
    value TEXT,
    confidence REAL
);
CREATE INDEX IF NOT EXISTS brain_facts_by_project ON brain_item_facts(project_id);
CREATE INDEX IF NOT EXISTS brain_facts_by_deal ON brain_item_facts(deal_id);

CREATE TABLE IF NOT EXISTS brain_evidence (
    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    line_from INTEGER NOT NULL,
    line_to INTEGER NOT NULL,
    quote_raw TEXT NOT NULL,
    quote_clean TEXT
);
CREATE INDEX IF NOT EXISTS brain_evidence_by_item ON brain_evidence(item_id);

CREATE TABLE IF NOT EXISTS brain_projects (
    project_id TEXT PRIMARY KEY,
    area_id TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT,
    csm_id TEXT,
    start_on TEXT,
    planned_end_on TEXT
);
CREATE TABLE IF NOT EXISTS brain_deals (
    deal_id TEXT PRIMARY KEY,
    area_id TEXT NOT NULL,
    name TEXT,
    industry TEXT,
    stage TEXT,
    owner_id TEXT,
    value_inr INTEGER,
    tags TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS brain_revenue (
    area_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    month TEXT NOT NULL,
    amount_inr INTEGER NOT NULL,
    PRIMARY KEY (area_id, project_id, month)
);

CREATE TABLE IF NOT EXISTS brain_review_queue (
    review_id TEXT PRIMARY KEY,
    area_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('translation', 'low_confidence', 'contradiction', 'unrouted')),
    proposed TEXT NOT NULL,
    reason TEXT,
    confidence REAL,
    assigned_to TEXT,
    due_on TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    queued_at TEXT,
    decided_by TEXT,
    decided_at TEXT,
    edited TEXT,
    edited_by TEXT,
    item_id TEXT
);

CREATE TABLE IF NOT EXISTS brain_playbooks (
    playbook_id TEXT PRIMARY KEY,
    source_area_id TEXT NOT NULL,
    deal_id TEXT NOT NULL UNIQUE,
    client_label TEXT,
    industry TEXT,
    outcome TEXT,
    revenue_inr INTEGER,
    sections TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    run_id TEXT,
    saved_at TEXT
);
CREATE TABLE IF NOT EXISTS brain_checklist (
    checklist_id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    question TEXT NOT NULL,
    why TEXT,
    learned_from TEXT NOT NULL DEFAULT '[]',
    industries TEXT NOT NULL DEFAULT '[]',
    UNIQUE (topic, question)
);
