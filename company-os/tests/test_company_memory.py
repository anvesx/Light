"""Tests for company_memory: items by area, links, runs, append-only steps, scoping."""
import os
import sqlite3
import tempfile
import unittest

from control_plane.company_memory import AreaDenied, DB_PATH, MemoryStore, ScopedMemory


class MemoryTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.mem = MemoryStore(os.path.join(tmp.name, "mem.db"))
        self.addCleanup(self.mem.close)


class TestItems(MemoryTestCase):
    def test_default_path_and_fixed_areas(self):
        self.assertTrue(DB_PATH.endswith("company_memory/company_memory.db"))
        kinds = {a["area_id"]: a["kind"] for a in self.mem.areas()}
        self.assertEqual(kinds, {"devx-internal": "internal", "hold": "hold", "playbooks": "library"})

    def test_add_and_filter(self):
        self.mem.ensure_area("C01", "Acme")
        a = self.mem.add_item("C01", "question", "Which gateway?", topic="payment-gateway", created_at="2026-05-01")
        b = self.mem.add_item("C01", "decision", "Use Razorpay", topic="payment-gateway", created_at="2026-06-01",
                              status="done", owner_id="P01", source="meeting", source_ref="M1")
        c = self.mem.add_item("C01", "fact", "Launch in Q4", topic="launch-date", created_at="2026-07-01")
        self.mem.add_item("C02", "fact", "Other client", created_at="2026-07-01")
        self.assertIsInstance(a, str)
        self.assertEqual([i["item_id"] for i in self.mem.items("C01")], [a, b, c])
        self.assertEqual([i["item_id"] for i in self.mem.items("C01", kinds="decision")], [b])
        self.assertEqual([i["item_id"] for i in self.mem.items("C01", kinds=["fact", "question"])], [a, c])
        self.assertEqual([i["item_id"] for i in self.mem.items("C01", status="done")], [b])
        self.assertEqual([i["item_id"] for i in self.mem.items("C01", topic="payment-gateway")], [a, b])
        self.assertEqual([i["item_id"] for i in self.mem.items("C01", before="2026-06-01")], [a])
        self.assertEqual(self.mem.get_item(b)["owner_id"], "P01")
        self.assertIsNone(self.mem.get_item("nope"))
        self.assertEqual(self.mem.items([]), [])

    def test_before_accepts_date_time(self):
        a = self.mem.add_item("C01", "fact", "x", created_at="2026-10-19T08:00")
        self.mem.add_item("C01", "fact", "y", created_at="2026-10-19T10:00")
        self.assertEqual([i["item_id"] for i in self.mem.items("C01", before="2026-10-19T09:00")], [a])

    def test_ids_are_stable_strings(self):
        first = self.mem.add_item("C01", "fact", "a")
        self.mem.reset()
        self.assertEqual(self.mem.add_item("C01", "fact", "a"), first)

    def test_given_id_is_idempotent_and_keeps_one_area(self):
        self.mem.add_item("C01", "fact", "a", item_id="m1/F1")
        self.assertEqual(self.mem.add_item("C01", "fact", "a", item_id="m1/F1"), "m1/F1")
        self.assertEqual(len(self.mem.items("C01")), 1)
        with self.assertRaises(ValueError):
            self.mem.add_item("C02", "fact", "a", item_id="m1/F1")

    def test_set_status(self):
        i = self.mem.add_item("C01", "task", "do it")
        self.mem.set_item_status(i, "done")
        self.assertEqual(self.mem.get_item(i)["status"], "done")

    def test_library_kind_and_new_link_types(self):
        self.assertEqual(self.mem.ensure_area("playbooks"), "playbooks")
        self.mem.ensure_area("lib2", kind="library")
        self.mem.ensure_area("C01")
        a = self.mem.add_item("C01", "fact", "A")
        b = self.mem.add_item("C01", "fact", "B")
        self.mem.add_link(a, "contradicts", b)
        self.mem.add_link(a, "same_as", b)
        self.assertEqual({l["rel"] for l in self.mem.links_of(a)}, {"contradicts", "same_as"})

    def test_area_kind_validated(self):
        with self.assertRaises(ValueError):
            self.mem.ensure_area("X", kind="bogus")


class TestLinks(MemoryTestCase):
    def test_links_both_ends(self):
        q = self.mem.add_item("C01", "question", "q")
        d = self.mem.add_item("C01", "decision", "d")
        self.mem.add_link(d, "answers", q, note="settled")
        self.mem.add_link(d, "answers", q)  # repeat is ignored
        self.assertEqual(len(self.mem.links_of(q)), 1)
        link = self.mem.links_of(d)[0]
        self.assertEqual((link["from_id"], link["rel"], link["to_id"], link["note"]), (d, "answers", q, "settled"))

    def test_bad_rel_and_missing_item(self):
        a = self.mem.add_item("C01", "fact", "a")
        with self.assertRaises(ValueError):
            self.mem.add_link(a, "likes", a)
        with self.assertRaises(KeyError):
            self.mem.add_link(a, "about", "ghost")


class TestRuns(MemoryTestCase):
    def test_run_lifecycle_and_steps(self):
        run = self.mem.start_run("meeting_prep", "request", "P05", "C01", "2026-10-19T09:00")
        self.assertEqual(self.mem.get_run(run)["status"], "running")
        self.assertEqual(self.mem.log_step(run, "model_call", {"n": 1}), 1)
        self.assertEqual(self.mem.log_step(run, "tool_call", {"name": "x"}), 2)
        self.assertEqual(self.mem.log_step(run, 3, {}), 3)
        self.mem.end_run(run, "done", 0.02, 100, 50, "2026-10-19T09:05")
        steps = self.mem.run_steps(run)
        self.assertEqual([s["seq"] for s in steps], [1, 2, 3])
        self.assertEqual(steps[0]["detail"], {"n": 1})
        self.assertEqual(steps[2]["step"], 3)
        done = self.mem.get_run(run)
        self.assertEqual((done["status"], done["cost_usd"], done["tokens_in"], done["ended_at"]),
                         ("done", 0.02, 100, "2026-10-19T09:05"))

    def test_seq_per_run(self):
        r1 = self.mem.start_run("a", "timer", "system", "C01", "t")
        r2 = self.mem.start_run("a", "timer", "system", "C01", "t")
        self.mem.log_step(r1, "s", {})
        self.assertEqual(self.mem.log_step(r2, "s", {}), 1)

    def test_steps_are_append_only(self):
        run = self.mem.start_run("a", "timer", "system", "C01", "t")
        self.mem.log_step(run, "s", {})
        public = [n for n in dir(self.mem) if not n.startswith("_")]
        self.assertFalse([n for n in public if "step" in n and n not in ("log_step", "run_steps")])
        with self.assertRaises(sqlite3.DatabaseError):
            self.mem.conn.execute("UPDATE run_steps SET detail = '{}'")
        with self.assertRaises(sqlite3.DatabaseError):
            self.mem.conn.execute("DELETE FROM run_steps")
        self.assertEqual(len(self.mem.run_steps(run)), 1)

    def test_unknown_run(self):
        with self.assertRaises(KeyError):
            self.mem.log_step("ghost", "s", {})
        with self.assertRaises(KeyError):
            self.mem.end_run("ghost", "done", 0, 0, 0, "t")


class TestCasesAndScores(MemoryTestCase):
    def test_cases(self):
        run = self.mem.start_run("finance_watch", "timer", "system", "C01", "t")
        case = self.mem.add_case(run, "finance_watch", "C01", "PR02 over hours", "high", {"hours": 130})
        rows = self.mem.cases(area_id="C01")
        self.assertEqual([r["case_id"] for r in rows], [case])
        self.assertEqual(rows[0]["status"], "open")
        self.assertIn("130", rows[0]["evidence"])
        self.assertEqual(self.mem.cases(area_id="C02"), [])

    def test_scores(self):
        self.mem.add_score("meeting_prep", "meeting_prep", "recall", 0.8, detail={"meetings": 5})
        rows = self.mem.scores(exam="meeting_prep")
        self.assertEqual((rows[0]["metric"], rows[0]["value"]), ("recall", 0.8))
        self.assertEqual(self.mem.scores(agent="other"), [])


class TestScoped(MemoryTestCase):
    def setUp(self):
        super().setUp()
        self.c1 = self.mem.add_item("C01", "question", "q1", topic="t", created_at="2026-05-01")
        self.c1b = self.mem.add_item("C01", "decision", "d1", topic="t", created_at="2026-06-01")
        self.c2 = self.mem.add_item("C02", "fact", "secret", created_at="2026-05-01")
        self.mem.add_link(self.c1b, "answers", self.c1)
        self.mem.add_link(self.c1, "about", self.c2)  # link across areas
        self.scope = self.mem.scoped(["C01"])

    def test_returns_scoped_memory(self):
        self.assertIsInstance(self.scope, ScopedMemory)

    def test_reads_allowed_area(self):
        self.assertEqual(len(self.scope.items("C01")), 2)
        self.assertEqual([i["item_id"] for i in self.scope.items("C01", kinds="decision", topic="t", before="2026-07-01")],
                         [self.c1b])
        self.assertEqual(self.scope.get_item(self.c1)["text"], "q1")
        self.assertEqual(len(self.scope.items()), 2)

    def test_denies_other_area(self):
        with self.assertRaises(AreaDenied):
            self.scope.items("C02")
        with self.assertRaises(AreaDenied):
            self.scope.items("hold")
        with self.assertRaises(AreaDenied):
            self.scope.get_item(self.c2)
        with self.assertRaises(AreaDenied):
            self.scope.links_of(self.c2)

    def test_links_hide_other_areas(self):
        links = self.scope.links_of(self.c1)
        self.assertEqual([(l["from_id"], l["rel"], l["to_id"]) for l in links], [(self.c1b, "answers", self.c1)])

    def test_multi_area_and_empty_scope(self):
        both = self.mem.scoped(["C01", "C02"])
        self.assertEqual(len(both.items()), 3)
        self.assertEqual(self.mem.scoped([]).items(), [])

    def test_reset_empties_everything(self):
        self.mem.reset()
        self.assertEqual(self.mem.items(), [])
        self.assertEqual(self.mem.links_of(self.c1), [])
        self.assertEqual({a["area_id"] for a in self.mem.areas()}, {"devx-internal", "hold", "playbooks"})


if __name__ == "__main__":
    unittest.main()
