"""Tests for the git activity data: rows, links, repeatability, old tables unchanged, planted delivery cases."""
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta

from company_data.generate_dummy_data import build
from company_data.generate_git_activity import GIT_RULES, behind_flags, first_stable_flag
from company_data.simulated_today import TODAY

NEW = ["repos", "scope_items", "task_scope", "pull_requests", "deploys"]


def D(s):
    return date.fromisoformat(s)


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


class GitActivityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.conn, cls.keys_path = make(cls.tmp, "a")
        cls.keys = json.load(open(cls.keys_path))["delivery_progress"]
        cls.case = {c["case_id"]: c for c in cls.keys["cases"]}
        cls.look = {c["case_id"]: c for c in cls.keys["look_alikes"]}

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        shutil.rmtree(cls.tmp)

    def q(self, sql, *a):
        return self.conn.execute(sql, a).fetchall()

    def test_new_tables_have_rows(self):
        for t in NEW:
            self.assertGreater(self.q(f"SELECT COUNT(*) FROM {t}")[0][0], 0, t)

    def test_foreign_keys_valid(self):
        self.assertEqual(self.q("PRAGMA foreign_key_check"), [])

    def test_links_and_names(self):
        self.assertEqual(self.q("SELECT COUNT(*) FROM pull_requests WHERE task_id IS NOT NULL AND "
                                "(branch NOT LIKE '%/' || task_id || '-%' OR title NOT LIKE '%' || task_id || '%')")[0][0], 0)
        self.assertEqual(self.q("SELECT COUNT(*) FROM pull_requests WHERE merged_at < opened_at")[0][0], 0)
        linked, total = self.q("SELECT (SELECT COUNT(DISTINCT task_id) FROM task_scope), COUNT(*) FROM tasks")[0]
        self.assertTrue(0.8 * total < linked < total)
        self.assertEqual(self.q("SELECT COUNT(*) FROM scope_items s JOIN projects p USING(project_id) "
                                "WHERE s.due_on > p.planned_end_on")[0][0], 0)
        self.assertEqual({r[0] for r in self.q("SELECT DISTINCT env FROM deploys")}, {"staging", "production"})

    def test_same_seed_same_git_data(self):
        conn2, _ = make(self.tmp, "b")
        for t in NEW:
            self.assertEqual(table_hash(self.conn, t), table_hash(conn2, t), t)
        conn2.close()

    def test_existing_tables_unchanged(self):
        conn0, keys0 = make(self.tmp, "c", git_activity=False)
        for t in NEW:
            self.assertEqual(conn0.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0], 0)
        tables = [r[0] for r in conn0.execute("SELECT name FROM sqlite_master WHERE type='table'") if r[0] not in NEW]
        for t in tables:
            self.assertEqual(table_hash(self.conn, t), table_hash(conn0, t), t)
        old, new = json.load(open(keys0)), json.load(open(self.keys_path))
        self.assertEqual({k: v for k, v in new.items() if k != "delivery_progress"}, old)
        conn0.close()

    def test_del1_unbilled_work(self):
        c = self.case["DEL-1"]
        sql = ("SELECT project_id, COUNT(*) FROM pull_requests WHERE task_id IS NULL AND merged_at IS NOT NULL "
               "AND lines_changed >= ? AND title NOT LIKE 'chore%' AND substr(merged_at,1,10) <= ? GROUP BY 1")
        seen = dict(self.q(sql, GIT_RULES["chore_max_lines"], c["first_detectable_on"]))
        self.assertGreaterEqual(seen[c["project_id"]], GIT_RULES["unbilled_prs"])
        before = dict(self.q(sql, GIT_RULES["chore_max_lines"], (D(c["first_detectable_on"]) - timedelta(days=1)).isoformat()))
        self.assertLess(before.get(c["project_id"], 0), GIT_RULES["unbilled_prs"])
        final = dict(self.q(sql, GIT_RULES["chore_max_lines"], TODAY))
        self.assertEqual([p for p, n in final.items() if n >= GIT_RULES["unbilled_prs"]], [c["project_id"]])

    def test_del2_rework(self):
        c = self.case["DEL-2"]
        sql = ("SELECT ts.scope_item_id, COUNT(*) FROM pull_requests p JOIN task_scope ts USING(task_id) "
               "WHERE p.after_meeting_id IS NOT NULL AND substr(p.opened_at,1,10) <= ? GROUP BY 1")
        seen = dict(self.q(sql, c["first_detectable_on"]))
        self.assertGreaterEqual(seen[c["scope_item_id"]], GIT_RULES["rework_prs"])
        final = dict(self.q(sql, TODAY))
        self.assertEqual([i for i, n in final.items() if n >= GIT_RULES["rework_prs"]], [c["scope_item_id"]])
        late = self.q("SELECT COUNT(*) FROM pull_requests p JOIN meetings m ON m.meeting_id = p.after_meeting_id "
                      "WHERE substr(p.opened_at,1,10) <= substr(m.start_at,1,10)")[0][0]
        self.assertEqual(late, 0)

    def pace(self, pid):
        start, end = self.q("SELECT start_on, planned_end_on FROM projects WHERE project_id=?", pid)[0]
        merged = {t: D(d[:10]) for t, d in self.q(
            "SELECT p.task_id, MIN(p.merged_at) FROM pull_requests p JOIN task_scope USING(task_id) "
            "WHERE p.merged_at IS NOT NULL GROUP BY 1") if self.q("SELECT 1 FROM tasks WHERE task_id=? AND project_id=?", t, pid)}
        hours = dict(self.q("SELECT t.task_id, t.estimate_hours FROM tasks t JOIN task_scope USING(task_id) "
                            "WHERE t.project_id=?", pid))
        return behind_flags(D(start), D(end), D(TODAY), merged, hours)

    def test_del3_behind_deadline(self):
        c = self.case["DEL-3"]
        flags = self.pace(c["project_id"])
        self.assertEqual(first_stable_flag(flags).isoformat(), c["first_detectable_on"])
        self.assertTrue(flags[max(flags)][0])
        self.assertGreater(D(c["projected_finish"]), D(self.q("SELECT planned_end_on FROM projects WHERE project_id=?",
                                                              c["project_id"])[0][0]))

    def test_look_alikes(self):
        l1, l2, l3 = self.look["DEL-L1"], self.look["DEL-L2"], self.look["DEL-L3"]
        chores = self.q("SELECT COUNT(*), MAX(lines_changed) FROM pull_requests WHERE project_id=? AND task_id IS NULL",
                        l1["project_id"])[0]
        self.assertEqual(chores[0], l1["count"])
        self.assertLess(chores[1], GIT_RULES["chore_max_lines"])
        n = self.q("SELECT COUNT(*) FROM pull_requests p JOIN task_scope ts USING(task_id) "
                   "WHERE p.after_meeting_id IS NOT NULL AND ts.scope_item_id=?", l2["scope_item_id"])[0][0]
        self.assertEqual(n, 2)
        flags = self.pace(l3["project_id"])
        self.assertFalse(any(f[0] for f in flags.values()))
        self.assertNotIn(l3["project_id"], {c["project_id"] for c in self.case.values() if c["case_id"] == "DEL-3"})


if __name__ == "__main__":
    unittest.main()
