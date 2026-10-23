"""Approval queue: risky tool calls wait here until a person decides."""
import json

from ._sqlite_open import open_db

DEFAULT_NOW = "2026-10-19T09:00"  # used when no simulated clock is given


class Approvals:
    def __init__(self, path=None, clock=None):
        from . import DB_PATH
        self.conn = open_db(path or DB_PATH)
        self.clock = clock
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS approvals (approval_id TEXT PRIMARY KEY, run_id TEXT, agent TEXT, tool TEXT,"
            " args TEXT, reason TEXT, status TEXT NOT NULL DEFAULT 'pending', requested_at TEXT,"
            " decided_by TEXT, decided_at TEXT)")
        self.conn.commit()

    def close(self):
        self.conn.close()

    def reset(self):
        with self.conn:
            self.conn.execute("DELETE FROM approvals")

    def _now(self):
        return self.clock.now if self.clock is not None else DEFAULT_NOW

    def _row(self, row):
        return {**dict(row), "args": json.loads(row["args"])}

    def request(self, run_id, agent, tool, args, reason):
        n = self.conn.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] + 1
        approval_id = f"A{n:06d}"
        with self.conn:
            self.conn.execute(
                "INSERT INTO approvals (approval_id, run_id, agent, tool, args, reason, requested_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (approval_id, run_id, agent, tool, json.dumps(args, sort_keys=True), reason, self._now()))
        return approval_id

    def get(self, approval_id):
        row = self.conn.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone()
        return self._row(row) if row else None

    def pending(self):
        rows = self.conn.execute("SELECT * FROM approvals WHERE status = 'pending' ORDER BY approval_id")
        return [self._row(r) for r in rows]

    def decide(self, approval_id, approved, by_person_id):
        """Approve or reject one waiting request. A request can be decided only once."""
        current = self.get(approval_id)
        if current is None:
            raise KeyError(approval_id)
        if current["status"] != "pending":
            raise ValueError(f"{approval_id} is already {current['status']}")
        with self.conn:
            self.conn.execute("UPDATE approvals SET status = ?, decided_by = ?, decided_at = ? WHERE approval_id = ?",
                              ("approved" if approved else "rejected", by_person_id, self._now(), approval_id))
        return self.get(approval_id)
