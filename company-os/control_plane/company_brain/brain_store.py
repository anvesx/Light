"""Brain store: sources and their lines, items with evidence, projects, deals, review queue, playbook library."""
import json
from datetime import date, timedelta
from pathlib import Path

LIBRARY = "playbooks"
STATES = ("active", "unconfirmed", "superseded", "resolved", "dropped")
LOW_CONFIDENCE = 0.6  # below this an item is stored as unconfirmed
ITEM_KINDS = ("decision", "requirement", "blocker", "question", "commitment", "fact", "risk", "money", "sentiment")
PROJECT_COLS = ("project_id", "area_id", "name", "status", "csm_id", "start_on", "planned_end_on")
DEAL_COLS = ("deal_id", "area_id", "name", "industry", "stage", "owner_id", "value_inr", "tags")
REVIEW_KINDS = ("translation", "low_confidence", "contradiction", "unrouted")
EDITABLE = ("text", "value", "topic")
ADMIN_ROLES = ("ceo", "rnd_lead", "finance_lead")
FALLBACK_ADMIN = "P01"  # used only when no people table is wired in
REVIEW_DAYS = 3
PROPOSAL_KEYS = ("kind", "text", "topic", "line_from", "line_to", "quote_raw", "quote_clean")


def _list(areas):
    return [areas] if isinstance(areas, str) else list(areas)


def _in(column, values):
    return f"{column} IN ({','.join('?' * len(values))})"


class BrainStore:
    def __init__(self, memory_store, data_conn=None):
        """`data_conn` (company data) is optional; it lets review assignment find people and admins."""
        self.memory = memory_store
        self.data_conn = data_conn
        self.conn = memory_store.conn
        self.conn.executescript((Path(__file__).parent / "schema.sql").read_text())

    def _now(self):
        return self.memory._now()

    def _next_id(self, prefix, table, column):
        n = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] + 1
        while self.conn.execute(f"SELECT 1 FROM {table} WHERE {column} = ?", (f"{prefix}{n:06d}",)).fetchone():
            n += 1
        return f"{prefix}{n:06d}"

    # sources
    def add_source(self, area_id, kind, title, raw_text, *, origin_ref, occurred_at, participants, language,
                   lines, project_id=None, deal_id=None, received_at=None, submitted_by=None):
        if not isinstance(raw_text, str) or not raw_text:
            raise ValueError("a source needs raw text")
        self.memory.ensure_area(area_id)
        source_id = self._next_id("SRC-", "brain_sources", "source_id")
        with self.conn:
            self.conn.execute(
                "INSERT INTO brain_sources (source_id, area_id, kind, title, raw_text, origin_ref, occurred_at, received_at,"
                " participants, language, project_id, deal_id, status, submitted_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (source_id, area_id, kind, title, raw_text, origin_ref, occurred_at, received_at or self._now(),
                 json.dumps(participants or [], sort_keys=True), language, project_id, deal_id,
                 "held" if area_id == "hold" else "new", submitted_by))
            for n, line in enumerate(lines, start=1):
                self.conn.execute(
                    "INSERT INTO brain_source_lines (source_id, line_no, raw_speaker, raw_text, t_sec, lang) VALUES (?,?,?,?,?,?)",
                    (source_id, line.get("line_no", n), line.get("speaker"), line["text"], line.get("t_sec"), line.get("lang")))
        return source_id

    @staticmethod
    def _source_row(row):
        out = dict(row)
        out["participants"] = json.loads(out["participants"])
        return out

    def get_source(self, source_id):
        row = self.conn.execute("SELECT * FROM brain_sources WHERE source_id = ?", (source_id,)).fetchone()
        return self._source_row(row) if row else None

    def source_by_ref(self, origin_ref):
        row = self.conn.execute("SELECT * FROM brain_sources WHERE origin_ref = ? ORDER BY source_id", (origin_ref,)).fetchone()
        return self._source_row(row) if row else None

    def source_lines(self, source_id):
        rows = self.conn.execute("SELECT * FROM brain_source_lines WHERE source_id = ? ORDER BY line_no", (source_id,))
        return [{"line_no": r["line_no"], "speaker": r["raw_speaker"], "text": r["raw_text"], "t_sec": r["t_sec"],
                 "lang": r["lang"], "clean_text": r["clean_text"], "clean_speaker": r["clean_speaker"]} for r in rows]

    def set_clean_lines(self, source_id, lines):
        """Save clean text (and speaker). Raw text and raw speaker are never touched."""
        if self.get_source(source_id) is None:
            raise KeyError(source_id)
        with self.conn:
            for line in lines:
                cur = self.conn.execute(
                    "UPDATE brain_source_lines SET clean_text = ?, clean_speaker = ? WHERE source_id = ? AND line_no = ?",
                    (line["clean_text"], line.get("speaker"), source_id, line["line_no"]))
                if cur.rowcount == 0:
                    raise KeyError(f"{source_id} line {line['line_no']}")

    def set_source_status(self, source_id, status):
        with self.conn:
            cur = self.conn.execute("UPDATE brain_sources SET status = ? WHERE source_id = ?", (status, source_id))
        if cur.rowcount == 0:
            raise KeyError(source_id)

    def reassign_source(self, source_id, area_id):
        """Move a source from hold to a client area. Refused once it has items."""
        source = self.get_source(source_id)
        if source is None:
            raise KeyError(source_id)
        if source["area_id"] != "hold":
            raise ValueError("only a source on hold can be reassigned")
        target = self.conn.execute("SELECT kind FROM areas WHERE area_id = ?", (area_id,)).fetchone()
        if target is None or target["kind"] != "client":
            raise ValueError(f"{area_id!r} is not a client area")
        if self.conn.execute("SELECT 1 FROM brain_item_facts WHERE source_id = ?", (source_id,)).fetchone() or \
                self.conn.execute("SELECT 1 FROM brain_evidence WHERE source_id = ?", (source_id,)).fetchone():
            raise ValueError("this source already has items")
        with self.conn:
            self.conn.execute("UPDATE brain_sources SET area_id = ?, status = 'new' WHERE source_id = ?", (area_id, source_id))

    def sources(self, area_ids, *, status=None, kind=None):
        areas = _list(area_ids)
        if not areas:
            return []
        where, params = [_in("area_id", areas)], list(areas)
        for column, value in (("status", status), ("kind", kind)):
            if value is not None:
                where.append(f"{column} = ?")
                params.append(value)
        sql = "SELECT * FROM brain_sources WHERE " + " AND ".join(where) + " ORDER BY received_at, source_id"
        return [self._source_row(r) for r in self.conn.execute(sql, params)]

    # items
    def _check_evidence(self, source_id, area_id, line_from, line_to, quote_raw):
        source = self.get_source(source_id)
        if source is None:
            raise ValueError(f"evidence points to an unknown source {source_id!r}")
        if source["area_id"] != area_id:
            raise ValueError("evidence must come from a source in the same area")
        if not quote_raw or not str(quote_raw).strip():
            raise ValueError("evidence needs a raw quote")
        count = self.conn.execute("SELECT COUNT(*) FROM brain_source_lines WHERE source_id = ?", (source_id,)).fetchone()[0]
        if not 1 <= line_from <= line_to or (count and line_to > count):
            raise ValueError(f"bad line range {line_from}-{line_to}")

    def _insert_item(self, area_id, kind, text, *, topic, source_id, line_from, line_to, quote_raw, quote_clean,
                     confidence, project_id=None, deal_id=None, speaker_id=None, said_at=None, value=None, state=None,
                     review_kind="low_confidence"):
        self._check_evidence(source_id, area_id, line_from, line_to, quote_raw)
        self.memory.ensure_area(area_id)
        if state is None:
            state = "unconfirmed" if confidence is not None and confidence < LOW_CONFIDENCE else "active"
        if state not in STATES:
            raise ValueError(f"unknown state {state!r}")
        item_id = self.memory._next_id("I", "items", "item_id")
        self.conn.execute("INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?)",
                          (item_id, area_id, kind, text, topic, state, "brain", source_id, self._now(), speaker_id))
        self.conn.execute("INSERT INTO brain_item_facts VALUES (?,?,?,?,?,?,?,?)",
                          (item_id, source_id, project_id, deal_id, speaker_id, said_at,
                           None if value is None else str(value), confidence))
        self.conn.execute("INSERT INTO brain_evidence (item_id, source_id, line_from, line_to, quote_raw, quote_clean)"
                          " VALUES (?,?,?,?,?,?)", (item_id, source_id, line_from, line_to, quote_raw, quote_clean))
        if state == "unconfirmed":  # stored at once; the check list gets a row, nothing waits
            self._insert_review(area_id, source_id, review_kind, {"item_id": item_id}, "stored as unconfirmed", confidence,
                                None, item_id)
        return item_id

    def add_brain_item(self, area_id, kind, text, *, topic, source_id, line_from, line_to, quote_raw, quote_clean,
                       confidence, project_id=None, deal_id=None, speaker_id=None, said_at=None, value=None, state=None,
                       review_kind="low_confidence"):
        """Store an item, its facts and its first evidence in one transaction. No evidence, no item.

        Confidence under 0.6, or state="unconfirmed" (for example an untranslated line), stores it as unconfirmed
        and adds a row to the check list (review_kind "low_confidence" or "translation").
        """
        with self.conn:
            return self._insert_item(area_id, kind, text, topic=topic, source_id=source_id, line_from=line_from,
                                     line_to=line_to, quote_raw=quote_raw, quote_clean=quote_clean, confidence=confidence,
                                     project_id=project_id, deal_id=deal_id, speaker_id=speaker_id, said_at=said_at,
                                     value=value, state=state, review_kind=review_kind)

    def add_evidence(self, item_id, source_id, line_from, line_to, quote_raw, quote_clean):
        item = self.memory.get_item(item_id)
        if item is None or self._facts(item_id) is None:
            raise KeyError(item_id)
        self._check_evidence(source_id, item["area_id"], line_from, line_to, quote_raw)
        with self.conn:
            self.conn.execute("INSERT INTO brain_evidence (item_id, source_id, line_from, line_to, quote_raw, quote_clean)"
                              " VALUES (?,?,?,?,?,?)", (item_id, source_id, line_from, line_to, quote_raw, quote_clean))

    def set_state(self, item_id, state):
        if state not in STATES:
            raise ValueError(f"unknown state {state!r}")
        if self._facts(item_id) is None:
            raise KeyError(item_id)
        self.memory.set_item_status(item_id, state)

    def set_scope(self, item_id, *, project_id=None, deal_id=None):
        """Set an item's project and/or deal. A value of None keeps what is stored."""
        if self._facts(item_id) is None:
            raise KeyError(item_id)
        with self.conn:
            self.conn.execute("UPDATE brain_item_facts SET project_id = COALESCE(?, project_id), deal_id = COALESCE(?, deal_id)"
                              " WHERE item_id = ?", (project_id, deal_id, item_id))

    def _facts(self, item_id):
        row = self.conn.execute("SELECT * FROM brain_item_facts WHERE item_id = ?", (item_id,)).fetchone()
        return dict(row) if row else None

    def _item_dict(self, row):
        item = dict(row)
        item["state"] = item["status"]
        item["confirmed"] = item["status"] != "unconfirmed"
        facts = self._facts(item["item_id"]) or {}
        facts.pop("item_id", None)
        item["facts"] = facts
        item["evidence"] = [dict(e) for e in self.conn.execute(
            "SELECT source_id, line_from, line_to, quote_raw, quote_clean FROM brain_evidence WHERE item_id = ?"
            " ORDER BY evidence_id", (item["item_id"],))]
        return item

    def get_brain_item(self, item_id):
        row = self.conn.execute("SELECT i.* FROM items i JOIN brain_item_facts f USING (item_id) WHERE i.item_id = ?",
                                (item_id,)).fetchone()
        return self._item_dict(row) if row else None

    def brain_items(self, area_ids, *, kinds=None, state="active", topic=None, project_id=None, deal_id=None,
                    source_id=None, before=None):
        areas = _list(area_ids)
        if not areas:
            return []
        where, params = [_in("i.area_id", areas)], list(areas)
        if kinds is not None:
            kinds = _list(kinds)
            where.append(_in("i.kind", kinds))
            params += kinds
        if state == "active":  # live items: confirmed ones and unconfirmed ones (each row says which)
            where.append("i.status IN ('active', 'unconfirmed')")
            state = None
        elif state == "confirmed":
            state = "active"
        for clause, value in (("i.status = ?", state), ("i.topic = ?", topic), ("f.project_id = ?", project_id),
                              ("f.deal_id = ?", deal_id), ("f.source_id = ?", source_id), ("i.created_at < ?", before)):
            if value is not None:
                where.append(clause)
                params.append(value)
        sql = ("SELECT i.* FROM items i JOIN brain_item_facts f USING (item_id) WHERE " + " AND ".join(where) +
               " ORDER BY i.created_at, i.item_id")
        return [self._item_dict(r) for r in self.conn.execute(sql, params)]

    # entities
    def _upsert(self, table, columns, row, key):
        unknown = set(row) - set(columns)
        if unknown or key not in row or "area_id" not in row:
            raise ValueError(f"{table}: need {key} and area_id; unknown fields {sorted(unknown)}")
        self.memory.ensure_area(row["area_id"])
        if "tags" in row:
            row = {**row, "tags": json.dumps(list(row["tags"] or []))}
        names = list(row)
        sets = ",".join(f"{c} = excluded.{c}" for c in names if c != key)
        with self.conn:
            self.conn.execute(f"INSERT INTO {table} ({','.join(names)}) VALUES ({','.join('?' * len(names))})"
                              f" ON CONFLICT({key}) DO UPDATE SET {sets}", [row[c] for c in names])

    def upsert_project(self, **row):
        self._upsert("brain_projects", PROJECT_COLS, row, "project_id")

    def upsert_deal(self, **row):
        self._upsert("brain_deals", DEAL_COLS, row, "deal_id")

    def add_revenue(self, area_id, project_id, month, amount_inr):
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO brain_revenue VALUES (?,?,?,?)", (area_id, project_id, month, amount_inr))

    def projects(self, area_ids):
        areas = _list(area_ids)
        if not areas:
            return []
        sql = f"SELECT * FROM brain_projects WHERE {_in('area_id', areas)} ORDER BY project_id"
        return [dict(r) for r in self.conn.execute(sql, areas)]

    def deals(self, area_ids, *, stage=None, owner_id=None):
        areas = _list(area_ids)
        if not areas:
            return []
        where, params = [_in("area_id", areas)], list(areas)
        for column, value in (("stage", stage), ("owner_id", owner_id)):
            if value is not None:
                where.append(f"{column} = ?")
                params.append(value)
        sql = "SELECT * FROM brain_deals WHERE " + " AND ".join(where) + " ORDER BY deal_id"
        return [{**dict(r), "tags": json.loads(r["tags"])} for r in self.conn.execute(sql, params)]

    def revenue(self, area_ids):
        areas = _list(area_ids)
        if not areas:
            return []
        sql = f"SELECT * FROM brain_revenue WHERE {_in('area_id', areas)} ORDER BY area_id, project_id, month"
        return [dict(r) for r in self.conn.execute(sql, areas)]

    # review queue
    def _people(self, sql, *params):
        return self.data_conn.execute(sql, params).fetchone() if self.data_conn is not None else None

    def _first_admin(self):
        row = self._people("SELECT person_id FROM people WHERE role IN (?,?,?) ORDER BY person_id", *ADMIN_ROLES)
        return row["person_id"] if row else FALLBACK_ADMIN

    def _is_admin(self, person_id):
        row = self._people("SELECT 1 FROM people WHERE person_id = ? AND role IN (?,?,?)", person_id, *ADMIN_ROLES)
        return row is not None if self.data_conn is not None else person_id == FALLBACK_ADMIN

    def _devx_submitter(self, source):
        if source.get("submitted_by"):
            return source["submitted_by"]
        for p in source["participants"]:
            email, name = (p.get("email") or "").lower(), (p.get("name") or "").lower()
            row = (email and self._people("SELECT person_id FROM people WHERE lower(email) = ? AND is_devx = 1", email)) or \
                  (name and self._people("SELECT person_id FROM people WHERE lower(name) = ? AND is_devx = 1", name))
            if row:
                return row["person_id"]
        return None

    def _area_owner(self, area_id, source, proposed):
        project_id = source["project_id"] or proposed.get("project_id")
        deal_id = source["deal_id"] or proposed.get("deal_id")
        row = (project_id and self.conn.execute("SELECT csm_id FROM brain_projects WHERE project_id = ?", (project_id,)).fetchone())
        if row and row["csm_id"]:
            return row["csm_id"]
        row = (deal_id and self.conn.execute("SELECT owner_id FROM brain_deals WHERE deal_id = ?", (deal_id,)).fetchone())
        if row and row["owner_id"]:
            return row["owner_id"]
        row = self.conn.execute("SELECT csm_id FROM brain_projects WHERE area_id = ? AND csm_id IS NOT NULL ORDER BY project_id", (area_id,)).fetchone()
        if row:
            return row["csm_id"]
        row = self.conn.execute("SELECT owner_id FROM brain_deals WHERE area_id = ? AND owner_id IS NOT NULL ORDER BY deal_id", (area_id,)).fetchone()
        if row:
            return row["owner_id"]
        row = self._people("SELECT csm_id FROM clients WHERE client_id = ?", area_id)
        return row["csm_id"] if row and row["csm_id"] else None

    def _assignee(self, area_id, source, proposed, kind):
        if kind == "unrouted" or area_id == "hold":
            return self._first_admin()
        return self._devx_submitter(source) or self._area_owner(area_id, source, proposed) or self._first_admin()

    def _insert_review(self, area_id, source_id, kind, proposed, reason, confidence, assigned_to, item_id):
        if kind not in REVIEW_KINDS:
            raise ValueError(f"unknown review kind {kind!r}")
        source = self.get_source(source_id)
        if source is None or source["area_id"] != area_id:
            raise ValueError("the review must name a source in the same area")
        assigned_to = assigned_to or self._assignee(area_id, source, proposed, kind)
        due_on = (date.fromisoformat(source["received_at"][:10]) + timedelta(days=REVIEW_DAYS)).isoformat()
        review_id = self._next_id("RV-", "brain_review_queue", "review_id")
        self.conn.execute("INSERT INTO brain_review_queue (review_id, area_id, source_id, kind, proposed, reason, confidence,"
                          " assigned_to, due_on, queued_at, item_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                          (review_id, area_id, source_id, kind, json.dumps(proposed, sort_keys=True), reason, confidence,
                           assigned_to, due_on, self._now(), item_id))
        return review_id

    def queue_review(self, area_id, source_id, proposed, reason, confidence, *, kind, assigned_to=None, item_id=None):
        """Add a row to the check list. Nothing waits on it. The helper fills assignee and due date when it can.

        With item_id the row is about an item already stored: confirm sets it active, reject sets it dropped.
        Without item_id, accept stores the proposal as a new item.
        """
        with self.conn:
            return self._insert_review(area_id, source_id, kind, proposed, reason, confidence, assigned_to, item_id)

    def _review_dict(self, row):
        out = {**dict(row), "proposed": json.loads(row["proposed"]), "edited": json.loads(row["edited"]) if row["edited"] else None}
        out["overdue"] = out["status"] == "pending" and self._now()[:10] > out["due_on"]
        return out

    def get_review(self, review_id):
        row = self.conn.execute("SELECT * FROM brain_review_queue WHERE review_id = ?", (review_id,)).fetchone()
        return self._review_dict(row) if row else None

    def reviews(self, area_ids, *, status="pending", assigned_to=None):
        """Reviews in the areas. With assigned_to: that person's, plus every overdue one when the person is an Admin."""
        areas = _list(area_ids)
        if not areas:
            return []
        where, params = [_in("area_id", areas)], list(areas)
        if status is not None:
            where.append("status = ?")
            params.append(status)
        sql = "SELECT * FROM brain_review_queue WHERE " + " AND ".join(where) + " ORDER BY review_id"
        rows = [self._review_dict(r) for r in self.conn.execute(sql, params)]
        if assigned_to is not None:
            admin = self._is_admin(assigned_to)
            rows = [r for r in rows if r["assigned_to"] == assigned_to or (admin and r["overdue"])]
        return rows

    def unconfirmed_count(self, area_id, project_id=None, deal_id=None):
        """How many stored items in the area (optionally one project or deal) are still unconfirmed."""
        return len(self.brain_items([area_id], state="unconfirmed", project_id=project_id, deal_id=deal_id))

    def decide_review(self, review_id, accept, by_person_id, *, edited=None):
        """Close a check-list row. Never deletes.

        Row about a stored item: confirm sets it active, reject sets it dropped (a rejected contradiction also restores the older item). `edited` (text, value, topic) is applied first.
        Row with a proposal only: accept stores the item and returns its id, reject stores nothing.
        """
        review = self.get_review(review_id)
        if review is None:
            raise KeyError(review_id)
        if review["status"] != "pending":
            raise ValueError("this review is already decided")
        if edited and (not accept or set(edited) - set(EDITABLE)):
            raise ValueError(f"only an accepted review can be edited, and only these fields: {EDITABLE}")
        proposed = {**review["proposed"], **(edited or {})}
        item_id = review["item_id"]
        if accept and not item_id and any(k not in proposed for k in PROPOSAL_KEYS):
            raise ValueError(f"the proposal is missing one of {PROPOSAL_KEYS}")
        with self.conn:
            if item_id:
                for field in ("text", "topic"):
                    if field in (edited or {}):
                        self.conn.execute(f"UPDATE items SET {field} = ? WHERE item_id = ?", (edited[field], item_id))
                if "value" in (edited or {}):
                    self.conn.execute("UPDATE brain_item_facts SET value = ? WHERE item_id = ?", (str(edited["value"]), item_id))
                self.conn.execute("UPDATE items SET status = ? WHERE item_id = ?", ("active" if accept else "dropped", item_id))
                if not accept and review["kind"] == "contradiction":  # a person disagrees: the older statement stands again
                    self.conn.execute("UPDATE items SET status = 'active' WHERE item_id = ?", (review["proposed"]["older"],))
            elif accept:
                extra = {k: proposed[k] for k in ("project_id", "deal_id", "speaker_id", "said_at", "value") if k in proposed}
                item_id = self._insert_item(
                    review["area_id"], proposed["kind"], proposed["text"], topic=proposed["topic"],
                    source_id=review["source_id"], line_from=proposed["line_from"], line_to=proposed["line_to"],
                    quote_raw=proposed["quote_raw"], quote_clean=proposed["quote_clean"],
                    confidence=proposed.get("confidence", review["confidence"]), state="active", **extra)
            self.conn.execute(
                "UPDATE brain_review_queue SET status = ?, decided_by = ?, decided_at = ?, item_id = ?, edited = ?, edited_by = ?"
                " WHERE review_id = ?",
                ("accepted" if accept else "rejected", by_person_id, self._now(), item_id, json.dumps(edited, sort_keys=True) if edited else None,
                 by_person_id if edited else None, review_id))
        return item_id if accept else None

    def resolve_contradiction(self, item_a, item_b):
        """The newer statement wins. The older becomes superseded and both keep a `contradicts` link.

        Returns {"newer", "older", "review_id"}. The check-list row is for a person who wants to look; nothing waits.
        """
        rows = {}
        for item_id in (item_a, item_b):
            item = self.get_brain_item(item_id)
            if item is None:
                raise KeyError(item_id)
            source = self.get_source(item["facts"]["source_id"])
            rows[item_id] = (item, (item["facts"]["said_at"] or source["occurred_at"] or item["created_at"], item["created_at"], item_id))
        if rows[item_a][0]["area_id"] != rows[item_b][0]["area_id"]:
            raise ValueError("both items must be in the same area")
        older, newer = sorted((item_a, item_b), key=lambda i: rows[i][1])
        self.set_state(older, "superseded")
        self.memory.add_link(newer, "contradicts", older, note="newer statement wins")
        item = rows[newer][0]
        review_id = self.queue_review(item["area_id"], item["facts"]["source_id"], {"newer": newer, "older": older},
                                      "the newer statement replaced the older", None, kind="contradiction", item_id=newer)
        return {"newer": newer, "older": older, "review_id": review_id}

    # library
    def save_playbook(self, *, source_area_id, deal_id, client_label, industry, outcome, revenue_inr, sections, tags, run_id):
        old = self.conn.execute("SELECT playbook_id FROM brain_playbooks WHERE deal_id = ?", (deal_id,)).fetchone()
        playbook_id = old["playbook_id"] if old else self._next_id("PB-", "brain_playbooks", "playbook_id")
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO brain_playbooks VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (playbook_id, source_area_id, deal_id, client_label, industry, outcome, revenue_inr,
                 json.dumps(sections, sort_keys=True), json.dumps(list(tags)), run_id, self._now()))
        return playbook_id

    def playbooks(self, *, industry=None, outcome=None):
        where, params = [], []
        for column, value in (("industry", industry), ("outcome", outcome)):
            if value is not None:
                where.append(f"{column} = ?")
                params.append(value)
        sql = "SELECT * FROM brain_playbooks" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY deal_id"
        return [{**dict(r), "area_id": r["source_area_id"], "sections": json.loads(r["sections"]),
                 "tags": json.loads(r["tags"])} for r in self.conn.execute(sql, params)]

    def save_checklist_item(self, *, topic, question, why, learned_from, industries):
        old = self.conn.execute("SELECT checklist_id FROM brain_checklist WHERE topic = ? AND question = ?",
                                (topic, question)).fetchone()
        checklist_id = old["checklist_id"] if old else self._next_id("CK-", "brain_checklist", "checklist_id")
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO brain_checklist VALUES (?,?,?,?,?,?)",
                              (checklist_id, topic, question, why, json.dumps(list(learned_from)), json.dumps(list(industries))))
        return checklist_id

    def checklist(self, *, industry=None):
        rows = self.conn.execute("SELECT * FROM brain_checklist ORDER BY topic, checklist_id")
        out = [{**dict(r), "learned_from": json.loads(r["learned_from"]), "industries": json.loads(r["industries"])} for r in rows]
        return [c for c in out if industry is None or not c["industries"] or industry in c["industries"]]

    def is_deal_stage(self, source):
        """Deal-stage source: linked to a deal, or dated before its client's first signed SOW (else first win)."""
        if source.get("deal_id"):
            return True
        if self.data_conn is None:
            return False
        row = self.data_conn.execute(
            "SELECT COALESCE((SELECT MIN(signed_on) FROM sows WHERE client_id = :c AND signed_on IS NOT NULL),"
            " (SELECT MIN(won_on) FROM leads WHERE client_id = :c AND won_on IS NOT NULL)) AS d", {"c": source["area_id"]}).fetchone()
        day = (source.get("occurred_at") or source.get("received_at") or "")[:10]
        return bool(row and row["d"] and day and day < row["d"])

    def scoped(self, area_ids, *, hide_deal_stage=False):
        from .scoped_brain import ScopedBrain
        return ScopedBrain(self, area_ids, hide_deal_stage=hide_deal_stage)
