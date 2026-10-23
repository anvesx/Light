"""Private message outbox. Stands in for private Slack messages to DevX people."""
from ._sqlite_open import open_db

DEFAULT_NOW = "2026-10-19T09:00"  # used when no simulated clock is given


class Outbox:
    def __init__(self, path=None, clock=None):
        from . import DB_PATH
        self.conn = open_db(path or DB_PATH)
        self.clock = clock
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS outbox (msg_id TEXT PRIMARY KEY, to_person_id TEXT NOT NULL, text TEXT NOT NULL,"
            " run_id TEXT, agent TEXT, kind TEXT, created_at TEXT NOT NULL)")
        self.conn.commit()

    def close(self):
        self.conn.close()

    def reset(self):
        with self.conn:
            self.conn.execute("DELETE FROM outbox")

    def post(self, to_person_id, text, *, run_id, agent, kind):
        n = self.conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] + 1
        msg_id = f"M{n:06d}"
        now = self.clock.now if self.clock is not None else DEFAULT_NOW
        with self.conn:
            self.conn.execute("INSERT INTO outbox VALUES (?, ?, ?, ?, ?, ?, ?)",
                              (msg_id, to_person_id, text, run_id, agent, kind, now))
        return msg_id

    def messages(self, to_person_id=None):
        sql, params = "SELECT * FROM outbox", []
        if to_person_id is not None:
            sql, params = sql + " WHERE to_person_id = ?", [to_person_id]
        return [dict(r) for r in self.conn.execute(sql + " ORDER BY msg_id", params)]
