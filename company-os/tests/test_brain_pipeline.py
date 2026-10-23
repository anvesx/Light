"""Pipeline: agents run in order, missing agents are skipped, a hold source waits for an Admin, the manifest and trigger work."""
import unittest

from control_plane.company_brain import pipeline
from evaluation.run_all_exams import close_all
from control_plane.triggers.inbox_trigger import InboxTrigger
from control_plane.triggers.simulated_clock import Clock

from tests.brain_test_support import make_cos, manifest_row, receive_ref


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cos = make_cos()

    @classmethod
    def tearDownClass(cls):
        close_all(cls.cos)

    def test_process_source_runs_the_agents_in_order(self):
        sid = receive_ref(self.cos, "SRC01")["source_id"]
        out = pipeline.process_source(self.cos, sid)
        self.assertEqual([s["agent"] for s in out["steps"]], ["brain_cleaner", "brain_extractor", "brain_linker", "brain_playbook"])
        self.assertEqual([s["status"] for s in out["steps"]], ["done", "done", "skipped", "skipped"])
        self.assertTrue(out["steps"][0]["run_id"] and out["steps"][1]["summary"].startswith("8 items"))
        self.assertEqual(out["area_id"], "C04")

    def test_a_source_on_hold_is_not_processed(self):
        got = pipeline.ingest_file(self.cos, kind="plain", content="We need payment by UPI.", origin_ref="HOLD1")
        self.assertEqual(got["area_id"], "hold")
        self.assertTrue(got["held"])
        self.assertEqual(got["steps"], [])
        self.assertEqual(self.cos.brain.brain_items(["hold"]), [])

    def test_ingest_file_with_a_hint_processes_and_a_duplicate_does_not(self):
        first = pipeline.ingest_file(self.cos, kind="plain", content="We need payment by UPI.", origin_ref="P1", hint_area="C04")
        self.assertEqual(first["steps"][1]["status"], "done")
        again = pipeline.ingest_file(self.cos, kind="plain", content="We need payment by UPI.", origin_ref="P1", hint_area="C04")
        self.assertTrue(again["duplicate"])
        self.assertEqual(again["steps"], [])

    def test_history_manifest_sources_are_ingested(self):
        cos = make_cos()
        self.addCleanup(close_all, cos)
        out = pipeline.ingest_manifest(cos, history=True)
        self.assertEqual(len(out), 28)
        self.assertTrue(all(r["steps"][0]["status"] == "done" for r in out if r["area_id"] != "hold"))

    def test_nothing_blocks_on_a_person(self):
        pipeline.ingest_manifest(self.cos, rows=[manifest_row("SRC13")])
        source = self.cos.brain.source_by_ref("SRC13")
        self.assertEqual(source["status"], "extracted")
        states = {i["state"] for i in self.cos.brain.brain_items([source["area_id"]], source_id=source["source_id"])}
        self.assertEqual(states, {"active", "unconfirmed"})


class InboxTriggerTests(unittest.TestCase):
    def test_rows_arrive_once_when_the_clock_reaches_them(self):
        trigger = InboxTrigger()
        self.assertEqual(trigger.due(Clock("2026-10-19T09:00")), [])
        first = trigger.due(Clock("2026-10-19T10:00"))
        self.assertTrue(first)
        self.assertTrue(all(not r["history"] and r["arrives_at"] <= "2026-10-19T10:00" for r in first))
        self.assertEqual(trigger.due(Clock("2026-10-19T10:00")), [])
        later = trigger.due(Clock("2026-10-21T00:00"))
        self.assertTrue({r["origin_ref"] for r in later}.isdisjoint(r["origin_ref"] for r in first))


if __name__ == "__main__":
    unittest.main()
