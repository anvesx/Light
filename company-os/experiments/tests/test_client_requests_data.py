"""Tests for the client requests data: rows, links, repeatability, old tables unchanged, planted cases."""
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import unittest

from company_data.generate_client_requests import CR_RULES, FAKE_SECRET
from company_data.generate_dummy_data import build
from company_data.simulated_today import TODAY

NEW = ["project_profiles", "client_requests", "client_request_events", "access_checks", "task_blocks"]
SECRET_SQL = ("kind = 'client_reply' AND channel = 'slack' AND (text LIKE '%pw:%' OR text LIKE '%password:%' "
              "OR text LIKE '%api key:%')")


def table_hash(conn, t):
    h = hashlib.sha256()
    for r in conn.execute(f"SELECT * FROM {t} ORDER BY rowid"):
        h.update(repr(r).encode())
    return h.hexdigest()


def make(tmp, name, **kw):
    d = os.path.join(tmp, name)
    os.makedirs(d)
    path = build(os.path.join(d, "c.db"), **kw)
    return sqlite3.connect(path), os.path.join(d, "answer_keys.json")


class ClientRequestsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.conn, cls.keys_path = make(cls.tmp, "a")
        cls.keys = json.load(open(cls.keys_path))["client_requests"]
        cls.case = {c["case_id"]: c for c in cls.keys["cases"]}
        cls.look = {c["case_id"]: c for c in cls.keys["look_alikes"]}

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        shutil.rmtree(cls.tmp)

    def q(self, sql, *a):
        return self.conn.execute(sql, a).fetchall()

    def test_new_tables_have_rows_and_valid_links(self):
        for t in NEW:
            self.assertGreater(self.q(f"SELECT COUNT(*) FROM {t}")[0][0], 0, t)
        self.assertEqual(self.q("PRAGMA foreign_key_check"), [])
        self.assertEqual(self.q("SELECT COUNT(*) FROM client_requests r JOIN people p ON p.person_id = r.owner_contact_id "
                                "WHERE p.role != 'client_contact' OR p.client_id != r.client_id")[0][0], 0)
        self.assertEqual(self.q("SELECT COUNT(*) FROM client_request_events WHERE at > ?", TODAY + "T23:59")[0][0], 0)

    def test_story_matches_project_profile(self):
        bad = self.q("SELECT COUNT(*) FROM client_requests r JOIN project_profiles p USING(project_id) WHERE "
                     "(r.kind IN ('shopify_collaborator_access','theme_access','app_install_approval') AND p.platform != 'shopify') "
                     "OR (r.kind = 'dns_record' AND p.uses_client_domain = 0) OR (r.kind = 'cloud_role' AND p.uses_client_cloud = 0)")
        self.assertEqual(bad[0][0], 0)

    def test_same_seed_same_rows(self):
        conn2, keys2 = make(self.tmp, "b")
        for t in NEW:
            self.assertEqual(table_hash(self.conn, t), table_hash(conn2, t), t)
        self.assertEqual(json.load(open(keys2))["client_requests"], self.keys)
        conn2.close()

    def test_existing_tables_unchanged(self):
        conn0, keys0 = make(self.tmp, "c", client_requests=False)
        for t in NEW:
            self.assertEqual(conn0.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0], 0)
        tables = [r[0] for r in conn0.execute("SELECT name FROM sqlite_master WHERE type='table'") if r[0] not in NEW]
        self.assertGreater(len(tables), 20)
        for t in tables:
            self.assertEqual(table_hash(self.conn, t), table_hash(conn0, t), t)
        old, new = json.load(open(keys0)), json.load(open(self.keys_path))
        self.assertEqual({k: v for k, v in new.items() if k != "client_requests"}, old)
        conn0.close()

    def test_cr1_asked_twice(self):
        c = self.case["CR-1"]
        sql = ("SELECT a.request_id, b.request_id FROM client_requests a JOIN client_requests b "
               "ON a.project_id = b.project_id AND a.kind = b.kind AND a.title = b.title AND a.request_id < b.request_id "
               "AND a.requested_by != b.requested_by AND a.status != 'cancelled' AND b.status != 'cancelled' "
               "AND julianday(substr(b.created_at,1,10)) - julianday(substr(a.created_at,1,10)) <= ? "
               "AND substr(b.created_at,1,10) <= ?")
        seen = self.q(sql, CR_RULES["duplicate_window_days"], c["first_detectable_on"])
        self.assertEqual(seen, [tuple(c["request_ids"])])
        self.assertEqual(self.q(sql, CR_RULES["duplicate_window_days"], "2026-08-06"), [])
        self.assertEqual(self.q(sql, CR_RULES["duplicate_window_days"], TODAY), [tuple(c["request_ids"])])

    def stuck(self, day):
        return [r[0] for r in self.q(
            "SELECT request_id FROM client_requests r WHERE status IN ('open','asked','reminded') "
            "AND julianday(?) - julianday(substr(created_at,1,10)) >= ? "
            "AND EXISTS (SELECT 1 FROM client_request_events e WHERE e.request_id = r.request_id AND e.kind = 'reminder' "
            "AND substr(e.at,1,10) <= ?) "
            "AND EXISTS (SELECT 1 FROM task_blocks k WHERE k.request_id = r.request_id AND k.blocked_to IS NULL)",
            day, CR_RULES["stuck_days"], day)]

    def test_cr2_stuck(self):
        c = self.case["CR-2"]
        self.assertEqual(self.stuck(c["first_detectable_on"]), [c["request_id"]])
        self.assertEqual(self.stuck("2026-10-07"), [])
        self.assertEqual(self.stuck(TODAY), [c["request_id"]])

    def test_cr3_granted_but_failing(self):
        c = self.case["CR-3"]
        sql = ("SELECT r.request_id FROM client_requests r JOIN access_checks a USING(request_id) "
               "WHERE r.status = 'granted' AND a.result = 'fail' AND substr(a.at,1,10) <= ?")
        self.assertEqual([r[0] for r in self.q(sql, c["first_detectable_on"])], [c["request_id"]])
        self.assertEqual(self.q(sql, "2026-09-23"), [])
        self.assertEqual([r[0] for r in self.q(sql, TODAY)], [c["request_id"]])

    def test_cr4_secret_in_chat(self):
        c = self.case["CR-4"]
        sql = f"SELECT request_id, text FROM client_request_events WHERE {SECRET_SQL} AND substr(at,1,10) <= ?"
        seen = self.q(sql, c["first_detectable_on"])
        self.assertEqual([r[0] for r in seen], [c["request_id"]])
        self.assertIn("pw: " + FAKE_SECRET, seen[0][1])
        self.assertEqual(self.q(sql, "2026-10-06"), [])
        self.assertEqual(len(self.q(sql, TODAY)), 1)

    def test_look_alikes_are_present_and_distinguishable(self):
        l1, l2 = self.look["CR-L1"], self.look["CR-L2"]
        n = self.q("SELECT COUNT(*) FROM client_request_events WHERE request_id = ? AND kind = 'reminder'", l1["request_id"])
        self.assertEqual(n[0][0], 1)
        row = self.q("SELECT status, granted_at, created_at FROM client_requests WHERE request_id = ?", l1["request_id"])[0]
        self.assertEqual(row[0], "verified")
        self.assertNotIn(l1["request_id"], {c.get("request_id") for c in self.case.values()})
        a, b = [self.q("SELECT project_id, kind, title, client_id FROM client_requests WHERE request_id = ?", i)[0]
                for i in l2["request_ids"]]
        self.assertEqual((a[0], a[1], a[3]), (b[0], b[1], b[3]))
        self.assertNotEqual(a[2], b[2])
        self.assertTrue(set(l2["request_ids"]).isdisjoint(self.case["CR-1"]["request_ids"]))


if __name__ == "__main__":
    unittest.main()
