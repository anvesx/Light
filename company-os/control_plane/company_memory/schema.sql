-- Company memory tables. Safe to run many times.
CREATE TABLE IF NOT EXISTS areas (
    area_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('client', 'internal', 'hold', 'library'))
);

-- Every item belongs to exactly one area.
CREATE TABLE IF NOT EXISTS items (
    item_id TEXT PRIMARY KEY,
    area_id TEXT NOT NULL REFERENCES areas(area_id),
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    topic TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    source TEXT,
    source_ref TEXT,
    created_at TEXT NOT NULL,
    owner_id TEXT
);
CREATE INDEX IF NOT EXISTS items_by_area ON items(area_id, created_at);

CREATE TABLE IF NOT EXISTS links (
    from_id TEXT NOT NULL,
    rel TEXT NOT NULL CHECK (rel IN ('supersedes', 'answers', 'refines', 'follows_up', 'about', 'contradicts', 'same_as')),
    to_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    note TEXT,
    PRIMARY KEY (from_id, rel, to_id)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    agent TEXT NOT NULL,
    trigger_kind TEXT,
    caller_id TEXT,
    area_id TEXT,
    started_at TEXT,
    ended_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    cost_usd REAL NOT NULL DEFAULT 0,
    tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0
);

-- The step label has no column type so a number or a text label is kept as given.
CREATE TABLE IF NOT EXISTS run_steps (
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    step,
    detail TEXT NOT NULL,
    at TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
-- Steps are append only: the database itself refuses an update or a delete.
CREATE TRIGGER IF NOT EXISTS run_steps_no_update BEFORE UPDATE ON run_steps
BEGIN SELECT RAISE(ABORT, 'run_steps is append-only'); END;
CREATE TRIGGER IF NOT EXISTS run_steps_no_delete BEFORE DELETE ON run_steps
BEGIN SELECT RAISE(ABORT, 'run_steps is append-only'); END;

CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    run_id TEXT,
    agent TEXT,
    area_id TEXT,
    subject TEXT,
    severity TEXT,
    evidence TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS scores (
    exam TEXT NOT NULL,
    agent TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL,
    at TEXT,
    detail TEXT
);
