"""Role scopes: Admin, CSM and Growth are enforced in the way-in check, the run's memory scope and the library."""
import os
import shutil
import sqlite3
import tempfile
import unittest

from company_data import DB_PATH
from control_plane.company_memory.memory_store import MemoryStore
from control_plane.connectors.people_directory import PeopleDirectory
from contract.types import Task
from control_plane.guardrails import role_scopes as rs
from control_plane.guardrails.access_policy import AccessPolicy
from control_plane.guardrails.way_in_check import WayInCheck
from lifecycle_kit.agent_pack import AgentPack
from core.agent_loop import Runtime

ROLES = rs.CONSOLE_ROLES


class Gateway:
    def budget_left(self, agent, caller_id):
        return 1.0


def insert_first_working(conn, options, sql):
    """Insert the first row variant the current schema accepts (F1 may widen the CHECK lists)."""
    for row in options:
        try:
            conn.execute(sql, row)
            return
        except sqlite3.IntegrityError:
            continue
    raise AssertionError("no row variant fits the schema")


def add_prospects(conn):
    """C2 values for C07 to C10 and their leads, added by the test."""
    for cid, name, status, lead, stage, owner in (
            ("C07", "CareNest Clinics", "prospect", "L20", "negotiation", "P03"),
            ("C08", "Zaika Foods", "prospect", "L21", "proposal", "P03"),
            ("C09", "Swasth Labs", "lost", "L22", "lost", "P04"),
            ("C10", "KiranaKart", "lost", "L23", "lost", "P30")):
        if conn.execute("SELECT 1 FROM clients WHERE client_id = ?", (cid,)).fetchone():
            continue
        insert_first_working(conn, [(cid, name, "x", None, None, status), (cid, name, "x", None, None, "active")],
                             "INSERT INTO clients VALUES (?,?,?,?,?,?)")
        insert_first_working(conn, [(lead, cid, "web", owner, stage, "2026-10-01", None, 1000000),
                                    (lead, cid, "web", owner, "proposal" if stage == "negotiation" else stage,
                                     "2026-10-01", None, 1000000)],
                             "INSERT INTO leads (lead_id,client_id,source,owner_id,stage,created_on,won_on,value_inr) VALUES (?,?,?,?,?,?,?,?)")
    conn.commit()


class RoleWorld(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "copy.db")
        shutil.copy(DB_PATH, path)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        add_prospects(self.conn)
        self.d = PeopleDirectory(self.conn)
        self.policy = AccessPolicy()
        self.policy.register_agent("brief", {"read"}, {"ceo", "csm", "growth", "system"}, {"ceo"}, reads_library=True)
        self.policy.register_agent("plain", {"read"}, {"ceo", "csm", "growth", "system"}, {"ceo"})
        self.policy.register_agent("finance", {"read"}, {"ceo", "finance_lead", "system"}, {"ceo"})
        self.policy.register_agent("travel", {"read"}, {"ceo", "csm", "growth"}, {"ceo"})
        self.gate = WayInCheck(self.d, Gateway(), self.policy)

    def admit(self, who, area, agent="plain"):
        return self.gate.admit(Task(agent, who, area, "go"))


class MatrixTests(unittest.TestCase):
    def test_pages_and_data_matrix(self):
        pages = {"home", "brain", "review", "meeting_prep", "deals", "live", "finance", "travel", "approvals", "runs"}
        for role in ROLES:
            for page in pages:
                self.assertEqual(rs.may_open_page(role, page), page in rs.PAGES[role], (role, page))
            for kind, roles in rs.DATA.items():
                self.assertEqual(rs.may_see(role, kind), role in roles, (role, kind))
        self.assertFalse(rs.may_open_page("nobody", "home"))
        self.assertFalse(rs.may_see("nobody", "travel_own"))

    def test_hard_lines(self):
        self.assertFalse(rs.may_see("csm", "finance"))
        self.assertFalse(rs.may_see("growth", "finance"))
        self.assertFalse(rs.may_see("csm", "library"))
        self.assertFalse(rs.may_see("growth", "project_items"))
        self.assertFalse(rs.may_see("csm", "deal_items"))
        self.assertEqual(rs.PAGES["admin"].count("runs"), 1)
        self.assertNotIn("runs", rs.PAGES["csm"] + rs.PAGES["growth"])


class RoleMappingTests(RoleWorld):
    def test_demo_people_map_to_roles(self):
        for pid, role in rs.DEMO_PEOPLE:
            self.assertEqual(rs.console_role(self.d, pid), role)

    def test_other_jobs_and_system_have_no_console(self):
        self.assertIsNone(rs.console_role(self.d, "system"))
        self.assertIsNone(rs.console_role(self.d, "P12"))
        self.assertIsNone(rs.console_role(self.d, "nobody"))
        for r in self.conn.execute("SELECT person_id, role FROM people"):
            self.assertEqual(rs.console_role(self.d, r[0]), rs.DB_ROLE_TO_CONSOLE.get(r[1]))


class AreaTests(RoleWorld):
    def test_neha_csm(self):
        areas = rs.readable_areas(self.d, "P05")
        self.assertTrue({"C01", "C04", "C06"} <= areas)
        self.assertFalse({"C02", "C07", "C09", rs.LIBRARY_AREA, "hold"} & areas)
        self.assertEqual(self.admit("P05", "C04").verdict, "allow")
        self.assertIn("no access", self.admit("P05", "C02").reason)
        self.assertIn("no access", self.admit("P05", rs.LIBRARY_AREA).reason)
        self.assertIn("no access", self.admit("P05", "C07").reason)
        self.assertEqual(self.admit("P05", "devx-internal", "travel").verdict, "allow")

    def test_neha_cannot_start_finance(self):
        r = self.admit("P05", "devx-internal", "finance")
        self.assertEqual(r.verdict, "deny")
        self.assertIn("may not start", r.reason)

    def test_rohan_growth(self):
        areas = rs.readable_areas(self.d, "P03")
        self.assertTrue({"C07", "C08", rs.LIBRARY_AREA} <= areas)
        self.assertFalse({"C01", "C04", "C09", "C10", "hold"} & areas)
        for area in ("C07", "C08", rs.LIBRARY_AREA):
            self.assertEqual(self.admit("P03", area).verdict, "allow", area)
        for area in ("C04", "C09", "C01"):
            self.assertIn("no access", self.admit("P03", area).reason, area)
        self.assertEqual(self.admit("P03", "devx-internal", "travel").verdict, "allow")
        self.assertEqual(self.admit("P03", "devx-internal", "finance").verdict, "deny")

    def test_aarav_admin_reads_everything(self):
        areas = rs.readable_areas(self.d, "P01")
        every = {r[0] for r in self.conn.execute("SELECT client_id FROM clients")}
        self.assertTrue(every <= areas)
        self.assertTrue({"devx-internal", "hold", rs.LIBRARY_AREA} <= areas)
        for area in ("C02", "C09", rs.LIBRARY_AREA, "hold"):
            self.assertEqual(self.admit("P01", area).verdict, "allow", area)

    def test_prospects_added_later_appear_without_code_changes(self):
        self.assertNotIn("C99", rs.readable_areas(self.d, "P03"))
        self.conn.execute("INSERT INTO clients VALUES ('C99','Later Co','x',NULL,NULL,'active')")
        self.conn.execute("INSERT INTO leads (lead_id,client_id,source,owner_id,stage,created_on,won_on,value_inr) VALUES ('L99','C99','web','P03','proposal','2026-10-18',NULL,5)")
        self.assertIn("C99", rs.readable_areas(self.d, "P03"))
        self.assertNotIn("C99", rs.readable_areas(self.d, "P05"))
        self.assertIn("C99", rs.readable_areas(self.d, "P01"))

    def test_growth_areas_come_from_the_database(self):
        owned = {r[0] for r in self.conn.execute(
            "SELECT l.client_id FROM leads l WHERE l.owner_id='P03' AND l.stage != 'won' AND l.client_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM leads w WHERE w.client_id = l.client_id AND w.stage='won')")}
        self.assertEqual(rs.readable_areas(self.d, "P03") - {"devx-internal", rs.LIBRARY_AREA}, owned)


class LibraryScopeTests(RoleWorld):
    def open_scope(self, who, agent, area):
        memory = MemoryStore(":memory:")
        memory.add_item(rs.LIBRARY_AREA, "note", "redacted playbook")
        memory.add_item("C04", "note", "raw client transcript")
        memory.add_item("C07", "note", "prospect note")
        rt = Runtime(Gateway(), memory, self.gate)
        ctx = rt.open_run(Task(agent, who, area, "go"))
        return ctx, memory

    def test_library_pack_gets_playbooks_for_rohan_and_system_never_neha(self):
        self.assertEqual(self.gate.extra_read_areas(Task("brief", "P03", "C07", "x")), {rs.LIBRARY_AREA})
        self.assertEqual(self.gate.extra_read_areas(Task("brief", "system", "C07", "x")), {rs.LIBRARY_AREA})
        self.assertEqual(self.gate.extra_read_areas(Task("brief", "P05", "C04", "x")), set())
        self.assertEqual(self.gate.extra_read_areas(Task("plain", "P03", "C07", "x")), set())

    def test_scoped_memory_for_rohan(self):
        ctx, _ = self.open_scope("P03", "brief", "C07")
        self.assertEqual([i["text"] for i in ctx.memory.items(rs.LIBRARY_AREA)], ["redacted playbook"])
        self.assertEqual(len(ctx.memory.items("C07")), 1)
        with self.assertRaises(Exception) as cm:
            ctx.memory.items("C04")  # no raw client transcripts for Growth
        self.assertEqual(type(cm.exception).__name__, "AreaDenied")

    def test_scoped_memory_for_neha_has_no_library_and_no_other_project(self):
        ctx, _ = self.open_scope("P05", "brief", "C04")
        for area in (rs.LIBRARY_AREA, "C02", "C07"):
            with self.assertRaises(Exception) as cm:
                ctx.memory.items(area)
            self.assertEqual(type(cm.exception).__name__, "AreaDenied", area)

    def test_plain_pack_for_rohan_has_no_library(self):
        ctx, _ = self.open_scope("P03", "plain", "C07")
        with self.assertRaises(Exception):
            ctx.memory.items(rs.LIBRARY_AREA)

    def test_pack_reads_library_flag_reaches_the_policy(self):
        class P(AgentPack):
            name, reads_library = "libpack", True

        class Q(AgentPack):
            name = "plainpack"
        p = AccessPolicy()
        P().register(Runtime(Gateway(), MemoryStore(":memory:"), self.gate), p)
        Q().register(Runtime(Gateway(), MemoryStore(":memory:"), self.gate), p)
        self.assertTrue(p.reads_library("libpack"))
        self.assertFalse(p.reads_library("plainpack"))
        self.assertFalse(AgentPack.reads_library)


if __name__ == "__main__":
    unittest.main()
