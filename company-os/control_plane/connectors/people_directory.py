"""Who is who and who may see which area. Backed by the people, clients and projects tables."""
SYSTEM_ID = "system"
SEE_ALL_ROLES = ("ceo", "rnd_lead")
INTERNAL_AREA = "devx-internal"
HOLD_AREA = "hold"
PUBLIC_FIELDS = ("person_id", "name", "email", "role", "team", "is_devx", "client_id", "manager_id")


class PeopleDirectory:
    def __init__(self, data_conn):
        self.conn = data_conn

    def _row(self, person_id):
        return self.conn.execute("SELECT * FROM people WHERE person_id = ?", (person_id,)).fetchone()

    def _client_areas(self):
        return {r[0] for r in self.conn.execute("SELECT client_id FROM clients")}

    def get(self, person_id):
        """Person as a dict without salary, or None. The person 'system' is known."""
        if person_id == SYSTEM_ID:
            return {"person_id": SYSTEM_ID, "name": "System", "email": None, "role": "system", "team": None,
                    "is_devx": 0, "client_id": None, "manager_id": None}
        row = self._row(person_id)
        return {k: row[k] for k in PUBLIC_FIELDS} if row else None

    def is_devx(self, person_id):
        row = self._row(person_id)
        return bool(row and row["is_devx"])

    def role(self, person_id):
        person = self.get(person_id)
        return person["role"] if person else None

    def manager_of(self, person_id):
        row = self._row(person_id)
        return row["manager_id"] if row else None

    def csm_of(self, area_id):
        row = self.conn.execute("SELECT csm_id FROM clients WHERE client_id = ?", (area_id,)).fetchone()
        return row["csm_id"] if row else None

    def lead_of(self, project_id):
        row = self.conn.execute("SELECT lead_id FROM projects WHERE project_id = ?", (project_id,)).fetchone()
        return row["lead_id"] if row else None

    def people_by_role(self, role):
        rows = self.conn.execute("SELECT person_id FROM people WHERE role = ? ORDER BY person_id", (role,))
        return [r[0] for r in rows]

    def client_access(self, person_id) -> set:
        """Area ids the person may read. CSM: own clients. Growth: own prospect and lost deals. Plus devx-internal."""
        if person_id == SYSTEM_ID:
            return self._client_areas() | {INTERNAL_AREA, HOLD_AREA}
        row = self._row(person_id)
        if row is None or not row["is_devx"]:
            return set()
        if row["role"] in SEE_ALL_ROLES:
            return self._client_areas() | {INTERNAL_AREA}
        if row["role"] == "csm":
            return self._csm_clients(person_id) | {INTERNAL_AREA}
        if row["role"] == "growth":
            return self._deal_clients(person_id) | {INTERNAL_AREA}
        return self._linked_clients(person_id) | {INTERNAL_AREA}

    def all_client_areas(self) -> set:
        return self._client_areas()

    def _csm_clients(self, pid):
        """Clients where the person is CSM on the client or on a project."""
        found = {r[0] for r in self.conn.execute("SELECT client_id FROM clients WHERE csm_id = ?", (pid,))}
        return found | {r[0] for r in self.conn.execute("SELECT client_id FROM projects WHERE csm_id = ?", (pid,))}

    def _deal_clients(self, pid):
        """Prospect and lost-deal clients the person owns: an open or lost lead, and the client never won."""
        return {r[0] for r in self.conn.execute(
            "SELECT client_id FROM leads l WHERE owner_id = ? AND stage != 'won' AND client_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM leads w WHERE w.client_id = l.client_id AND w.stage = 'won')", (pid,))}

    def _linked_clients(self, pid):
        queries = (
            "SELECT client_id FROM clients WHERE csm_id = ? OR account_manager_id = ?",
            "SELECT client_id FROM projects WHERE csm_id = ? OR lead_id = ?",
        )
        found = set()
        for sql in queries:
            found |= {r[0] for r in self.conn.execute(sql, (pid, pid))}
        found |= {r[0] for r in self.conn.execute(
            "SELECT p.client_id FROM tasks t JOIN projects p ON p.project_id = t.project_id WHERE t.assignee_id = ?",
            (pid,))}
        found |= {r[0] for r in self.conn.execute(
            "SELECT p.client_id FROM time_logs l JOIN tasks t ON t.task_id = l.task_id "
            "JOIN projects p ON p.project_id = t.project_id WHERE l.person_id = ?", (pid,))}
        return found
