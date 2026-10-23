"""SQLite company memory: items by area, links, runs, append-only run steps, cases, scores."""
import json
import sqlite3
from pathlib import Path

from .scoped_memory import ScopedMemory

HERE = Path(__file__).parent
DB_PATH = str(HERE / "company_memory.db")
DEFAULT_NOW = "2026-10-19T09:00"  # used when no simulated clock is given
RELS = ("supersedes", "answers", "refines", "follows_up", "about", "contradicts", "same_as")
AREA_KINDS = ("client", "internal", "hold", "library")
FIXED_AREAS = (("devx-internal", "DevX internal", "internal"), ("hold", "Hold: client not decided", "hold"),
               ("playbooks", "Playbook library", "library"))
TABLES = ("scores", "cases", "run_steps", "runs", "links", "items", "areas")


def _json(value):
    return value if isinstance(value, str) or value is None else json.dumps(value, sort_keys=True)


class MemoryStore:
    def __init__(self, path=DB_PATH, clock=None):
        """`clock` is any object with a `.now` string; it stamps rows that get no time."""
        self.path = str(path)
        self.clock = clock
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create()

    def _create(self):
        self.conn.executescript((HERE / "schema.sql").read_text())
        with self.conn:
            for area_id, name, kind in FIXED_AREAS:
                self.conn.execute("INSERT OR IGNORE INTO areas VALUES (?, ?, ?)", (area_id, name, kind))

    def reset(self):
        """Drop every table and build them again, empty."""
        brain = [r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'brain\\_%' ESCAPE '\\'")]
        with self.conn:
            for table in brain + list(TABLES):  # brain_* tables (company_brain) go first
                self.conn.execute(f"DROP TABLE IF EXISTS {table}")
        self._create()

    def close(self):
        self.conn.close()

    def _now(self):
        return self.clock.now if self.clock is not None else DEFAULT_NOW

    def _next_id(self, prefix, table, column):
        n = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] + 1
        while self.conn.execute(f"SELECT 1 FROM {table} WHERE {column} = ?", (f"{prefix}{n:06d}",)).fetchone():
            n += 1
        return f"{prefix}{n:06d}"

    # areas
    def ensure_area(self, area_id, name=None, kind=None):
        """Create the area if missing. Kind defaults to internal, hold or client by id."""
        if kind is None:
            kind = {"devx-internal": "internal", "hold": "hold", "playbooks": "library"}.get(area_id, "client")
        if kind not in AREA_KINDS:
            raise ValueError(f"unknown area kind {kind!r}")
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO areas VALUES (?, ?, ?)", (area_id, name or area_id, kind))
        return area_id

    def areas(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM areas ORDER BY area_id")]

    # items and links
    def add_item(self, area_id, kind, text, *, topic=None, status="open", source=None, source_ref=None,
                 created_at=None, owner_id=None, item_id=None):
        """Add an item. A given item_id that already exists is returned as is (safe to repeat)."""
        self.ensure_area(area_id)
        if item_id is not None:
            old = self.get_item(item_id)
            if old is not None:
                if old["area_id"] != area_id:
                    raise ValueError(f"item {item_id} already belongs to area {old['area_id']}")
                return item_id
        else:
            item_id = self._next_id("I", "items", "item_id")
        with self.conn:
            self.conn.execute(
                "INSERT INTO items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (item_id, area_id, kind, text, topic, status, source, source_ref,
                 created_at or self._now(), owner_id))
        return item_id

    def set_item_status(self, item_id, status):
        with self.conn:
            cur = self.conn.execute("UPDATE items SET status = ? WHERE item_id = ?", (status, item_id))
        if cur.rowcount == 0:
            raise KeyError(item_id)

    def get_item(self, item_id):
        row = self.conn.execute("SELECT * FROM items WHERE item_id = ?", (item_id,)).fetchone()
        return dict(row) if row else None

    def items(self, area_id=None, kinds=None, status=None, topic=None, before=None):
        """area_id: one id, a list of ids, or None for all. `before` keeps items created earlier."""
        where, params = [], []
        if area_id is not None:
            areas = [area_id] if isinstance(area_id, str) else list(area_id)
            if not areas:
                return []
            where.append(f"area_id IN ({','.join('?' * len(areas))})")
            params += areas
        if kinds is not None:
            kinds = [kinds] if isinstance(kinds, str) else list(kinds)
            where.append(f"kind IN ({','.join('?' * len(kinds))})")
            params += kinds
        for column, value in (("status", status), ("topic", topic)):
            if value is not None:
                where.append(f"{column} = ?")
                params.append(value)
        if before is not None:
            where.append("created_at < ?")
            params.append(before)
        sql = "SELECT * FROM items" + (" WHERE " + " AND ".join(where) if where else "")
        return [dict(r) for r in self.conn.execute(sql + " ORDER BY created_at, item_id", params)]

    def add_link(self, from_id, rel, to_id, *, created_at=None, note=None):
        if rel not in RELS:
            raise ValueError(f"unknown link type {rel!r}")
        for item_id in (from_id, to_id):
            if self.get_item(item_id) is None:
                raise KeyError(item_id)
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO links VALUES (?, ?, ?, ?, ?)",
                              (from_id, rel, to_id, created_at or self._now(), note))

    def links_of(self, item_id):
        """Links where the item is on either end."""
        rows = self.conn.execute(
            "SELECT * FROM links WHERE from_id = ? OR to_id = ? ORDER BY created_at, from_id, rel, to_id",
            (item_id, item_id))
        return [dict(r) for r in rows]

    def scoped(self, area_ids):
        return ScopedMemory(self, area_ids)

    # runs and steps
    def start_run(self, agent, trigger_kind, caller_id, area_id, started_at=None):
        run_id = self._next_id("R", "runs", "run_id")
        with self.conn:
            self.conn.execute(
                "INSERT INTO runs (run_id, agent, trigger_kind, caller_id, area_id, started_at) VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, agent, trigger_kind, caller_id, area_id, started_at or self._now()))
        return run_id

    def get_run(self, run_id):
        row = self.conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def runs(self, agent=None):
        sql, params = "SELECT * FROM runs", []
        if agent is not None:
            sql, params = sql + " WHERE agent = ?", [agent]
        return [dict(r) for r in self.conn.execute(sql + " ORDER BY run_id", params)]

    def end_run(self, run_id, status, cost_usd=0.0, tokens_in=0, tokens_out=0, ended_at=None):
        with self.conn:
            cur = self.conn.execute(
                "UPDATE runs SET status = ?, cost_usd = ?, tokens_in = ?, tokens_out = ?, ended_at = ? WHERE run_id = ?",
                (status, cost_usd, tokens_in, tokens_out, ended_at or self._now(), run_id))
        if cur.rowcount == 0:
            raise KeyError(run_id)

    def log_step(self, run_id, step, detail=None, at=None):
        """Append one step. Steps get seq 1, 2, 3... and can never be changed."""
        if self.get_run(run_id) is None:
            raise KeyError(run_id)
        with self.conn:
            seq = self.conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM run_steps WHERE run_id = ?",
                                    (run_id,)).fetchone()[0]
            self.conn.execute("INSERT INTO run_steps VALUES (?, ?, ?, ?, ?)",
                              (run_id, seq, step, json.dumps(detail or {}, sort_keys=True), at or self._now()))
        return seq

    def run_steps(self, run_id):
        rows = self.conn.execute("SELECT * FROM run_steps WHERE run_id = ? ORDER BY seq", (run_id,))
        return [{**dict(r), "detail": json.loads(r["detail"])} for r in rows]

    # cases and scores
    def add_case(self, run_id, agent, area_id, subject, severity, evidence, *, status="open", created_at=None):
        case_id = self._next_id("CASE", "cases", "case_id")
        with self.conn:
            self.conn.execute("INSERT INTO cases VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                              (case_id, run_id, agent, area_id, subject, severity, _json(evidence),
                               status, created_at or self._now()))
        return case_id

    def cases(self, area_id=None, agent=None):
        where, params = [], []
        for column, value in (("area_id", area_id), ("agent", agent)):
            if value is not None:
                where.append(f"{column} = ?")
                params.append(value)
        sql = "SELECT * FROM cases" + (" WHERE " + " AND ".join(where) if where else "")
        return [dict(r) for r in self.conn.execute(sql + " ORDER BY case_id", params)]

    def add_score(self, exam, agent, metric, value, *, at=None, detail=None):
        with self.conn:
            self.conn.execute("INSERT INTO scores VALUES (?, ?, ?, ?, ?, ?)",
                              (exam, agent, metric, value, at or self._now(), _json(detail)))

    def scores(self, exam=None, agent=None):
        where, params = [], []
        for column, value in (("exam", exam), ("agent", agent)):
            if value is not None:
                where.append(f"{column} = ?")
                params.append(value)
        sql = "SELECT * FROM scores" + (" WHERE " + " AND ".join(where) if where else "")
        return [dict(r) for r in self.conn.execute(sql + " ORDER BY rowid", params)]
