"""Per-person memory: short notes a person asked the agents to keep. Private to that person.
Only the person's own chat message may save one. Tool output and client text never reach this class."""
import re

from control_plane.company_brain.redaction import redact

MAX_CHARS = 300
MAX_LIVE = 50
RUN_LIMIT = 20
EVERYTHING = {"everything", "all", "everything about me", "all of it", "everything you know", "everything you remember"}


class PersonMemoryError(ValueError):
    pass


class PersonMemory:
    def __init__(self, store, data_conn=None):
        """`store` is the MemoryStore that holds the person_memory table; `data_conn` feeds the name redaction."""
        self.store = store
        self.data_conn = data_conn

    def remember(self, person_id, text, area_id=None, source_journey_id=None) -> dict:
        text = (text or "").strip()
        if not person_id:
            raise PersonMemoryError("a note needs a person")
        if not text:
            raise PersonMemoryError("there is nothing to remember: the text is empty")
        if len(text) > MAX_CHARS:
            raise PersonMemoryError(f"the note is {len(text)} characters long; the limit is {MAX_CHARS}")
        text = redact(text, self.data_conn)
        if not text:
            raise PersonMemoryError("nothing is left of the note after private details were removed")
        conn = self.store.conn
        with conn:
            live = conn.execute("SELECT COUNT(*) FROM person_memory WHERE person_id = ? AND deleted_at IS NULL",
                                (person_id,)).fetchone()[0]
            if live >= MAX_LIVE:
                raise PersonMemoryError(f"you already have {MAX_LIVE} notes; forget one before adding another")
            item_id = self.store._next_id("PM", "person_memory", "item_id")
            conn.execute("INSERT INTO person_memory (item_id, person_id, text, area_id, created_at, source_journey_id)"
                         " VALUES (?, ?, ?, ?, ?, ?)",
                         (item_id, person_id, text, area_id, self.store._now(), source_journey_id))
        return self._get(item_id)

    def list(self, person_id):
        """Live notes of one person, oldest first."""
        return self._live(person_id, "ORDER BY item_id")

    def forget(self, person_id, item_id=None, match=None) -> int:
        """Soft delete by id, or every live note whose text holds `match`. Returns how many were removed."""
        if item_id is None and not match:
            raise PersonMemoryError("say which note to forget: give an id or some words from it")
        needle = (match or "").lower()
        ids = [i["item_id"] for i in self.list(person_id) if (item_id is not None and i["item_id"] == item_id)
               or (item_id is None and needle in i["text"].lower())]
        return self._delete(ids)

    def forget_all(self, person_id) -> int:
        return self._delete([i["item_id"] for i in self.list(person_id)])

    def for_run(self, person_id, areas):
        """The newest 20 live notes with no area, or an area the run may read. Oldest first."""
        areas = set(areas or ())
        rows = [i for i in self._live(person_id, "ORDER BY item_id DESC") if i["area_id"] is None or i["area_id"] in areas]
        return list(reversed(rows[:RUN_LIMIT]))

    def _live(self, person_id, order):
        rows = self.store.conn.execute(
            f"SELECT * FROM person_memory WHERE person_id = ? AND deleted_at IS NULL {order}", (person_id,))
        return [dict(r) for r in rows]

    def _get(self, item_id) -> dict:
        return dict(self.store.conn.execute("SELECT * FROM person_memory WHERE item_id = ?", (item_id,)).fetchone())

    def _delete(self, ids) -> int:
        with self.store.conn:
            for item_id in ids:
                self.store.conn.execute("UPDATE person_memory SET deleted_at = ?, text = '' WHERE item_id = ?",
                                        (self.store._now(), item_id))
        return len(ids)


_REMEMBER = re.compile(r"^(?:remember(?:\s+that)?|don['’]?t\s+forget(?:\s+that)?)\b[\s,:-]*(.+)$", re.I | re.S)
_FROM_NOW_ON = re.compile(r"^from\s+now\s+on\b", re.I)
_LIST = re.compile(r"^what\s+(?:do|did|can)\s+you\s+(?:still\s+)?remember\b", re.I)
_FORGET = re.compile(r"^forget\b(?:\s+(?:that|about))?[\s,:-]*(.+)$", re.I | re.S)


def parse_request(message):
    """Rule-based, no model. Returns ("remember", text), ("list", None), ("forget", text) or None."""
    text = (message or "").strip()
    if _LIST.match(text):
        return ("list", None)
    if _FROM_NOW_ON.match(text):
        return ("remember", text)   # the whole sentence is the note
    found = _REMEMBER.match(text)
    if found and found.group(1).strip():
        return ("remember", found.group(1).strip())
    found = _FORGET.match(text)
    if found and found.group(1).strip():
        return ("forget", found.group(1).strip().rstrip(".!"))
    return None


def wants_everything(text) -> bool:
    return (text or "").strip().lower().rstrip(".!") in EVERYTHING
