"""Integration tests: one demo day runs end to end, and the exams runner scores every available pack."""
import contextlib
import io
import shutil
import tempfile
import unittest

from evaluation.run_all_exams import close_all, run_all
from run_demo import available_agents, run_day
from wiring.build_company_os import build_company_os


class DemoDayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = tempfile.mkdtemp(prefix="company_os_test_")
        cls.day = run_day(state_dir=cls.state)

    @classmethod
    def tearDownClass(cls):
        close_all(cls.day["cos"])
        shutil.rmtree(cls.state, ignore_errors=True)

    def statuses(self):
        return [r["status"] for r in self.day["runs"]]

    def test_day_runs_without_failed_runs(self):
        self.assertTrue(self.day["runs"])
        self.assertNotIn("failed", self.statuses())

    def test_people_receive_messages(self):
        self.assertGreaterEqual(len(self.day["messages"]), 1)

    def test_one_run_is_held_for_approval(self):
        self.assertIn("held", self.statuses())
        self.assertGreaterEqual(len(self.day["approvals"]), 1)

    def test_one_run_is_quiet(self):
        self.assertIn("quiet", self.statuses())

    def test_engineer_is_refused(self):
        self.assertEqual(self.day["refusal"]["status"], "refused")
        self.assertIn("refused", self.statuses())

    def test_the_v2_story_is_in_the_day(self):
        by = {(r["trigger"], r["agent"]): r for r in self.day["runs"]}
        self.assertEqual(by[("inbox", "brain_cleaner")]["status"], "done")
        self.assertEqual(by[("request", "meeting_prep")]["area"], "C04")   # Akbar, PR05
        self.assertEqual(by[("request", "deal_brief")]["area"], "C07")     # Anthony, CareNest
        self.assertEqual(by[("request", "travel_booking")]["status"], "held")
        self.assertEqual(by[("request", "finance_watch")]["status"], "refused")
        self.assertEqual(self.day["refusal"]["caller"], "P03")

    def test_cost_numbers_add_up(self):
        c = self.day["cost"]
        self.assertGreater(c["calls"], 0)
        self.assertEqual(c["cache_hits"] + c["cache_writes"], c["calls"])


class SeededBuildTests(unittest.TestCase):
    def test_seed_brain_fills_the_brain_through_the_pipeline(self):
        from evaluation.real_pipeline_brain import BRAIN_AGENTS
        cos = build_company_os(BRAIN_AGENTS, seed_brain=True)
        self.addCleanup(close_all, cos)
        self.assertIsNotNone(cos.brain.source_by_ref("SRC28"))
        self.assertIsNone(cos.brain.source_by_ref("SRC29"))   # today's sources arrive later
        self.assertGreaterEqual(len(cos.brain.playbooks()), 4)
        self.assertTrue(cos.brain.checklist())

    def test_default_build_leaves_the_brain_empty(self):
        cos = build_company_os(("meeting_prep",))
        self.addCleanup(close_all, cos)
        self.assertEqual(cos.brain.sources(["C04"]), [])


class ExamRunnerTests(unittest.TestCase):
    def test_every_available_pack_has_a_result(self):
        rows = run_all()
        available = set(available_agents()[0])
        scored = {r["agent"] for r in rows if r["passed"] is not None}
        self.assertTrue(available <= scored)
        self.assertTrue({"meeting_prep", "finance_watch", "spend_advisor"} <= scored)
        self.assertTrue(all(r["passed"] for r in rows if r["passed"] is not None), rows)

    def test_brain_exams_also_run_on_a_brain_from_the_real_pipeline(self):
        rows = {r["agent"]: r for r in run_all(("meeting_prep", "deal_brief", "live_copilot", "finance_watch"))}
        for name in ("meeting_prep", "deal_brief", "live_copilot"):
            self.assertIn("real_pipeline", rows[name])
            self.assertTrue(rows[name]["real_pipeline"]["passed"], rows[name]["real_pipeline"])
        self.assertNotIn("real_pipeline", rows["finance_watch"])
        self.assertNotIn("real_pipeline", run_all(("meeting_prep",), real_pipeline=False)[0])

    def test_real_sample_recorder_needs_yes(self):
        from evaluation import record_real_samples
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(record_real_samples.main([]), 1)


if __name__ == "__main__":
    unittest.main()
