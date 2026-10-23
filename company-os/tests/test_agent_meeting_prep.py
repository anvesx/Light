"""Tests for the meeting prep agent pack: full run, access, the check step, injection and the replay exam."""
import json
import tempfile
import unittest

from agents.meeting_prep.project_brief.replay_exam import run_exam
from wiring.build_company_os import build_company_os

AGENT = "meeting_prep"


def build():
    return build_company_os(agents=(AGENT,), state_dir=tempfile.mkdtemp(prefix="meeting_prep_test_"))


class MeetingPrepRunTests(unittest.TestCase):
    def setUp(self):
        self.cos = build()

    def steps(self, run_id, name):
        return [s["detail"] for s in self.cos.memory.run_steps(run_id) if s["step"] == name]

    def test_full_run_for_upcoming_event(self):
        result = self.cos.run(AGENT, "P10", "C02", inputs={"event_id": "EV113"})
        self.assertEqual(result.status, "done", result.reason)
        briefs = [m for m in self.cos.outbox.messages() if m["kind"] == "brief"]
        self.assertEqual(sorted(m["to_person_id"] for m in briefs), ["P06", "P10"])  # DevX attendees only
        self.assertIn("Questions to settle", briefs[0]["text"])
        self.assertIn("memory item I", briefs[0]["text"])
        # every read and every action is in the run steps, each with a verdict
        tools = self.steps(result.run_id, "tool")
        names = [t["name"] for t in tools]
        for read in ("upcoming_meeting", "project_open_items", "project_recent_decisions"):
            self.assertIn(read, names)
        self.assertEqual(names.count("send_private_message"), 2)
        self.assertTrue(all(t["verdict"] == "allow" for t in tools))
        labels = [s["step"] for s in self.cos.memory.run_steps(result.run_id)]
        for label in ("record", "understand", "decide", "parse", "check", "act", "remember"):
            self.assertIn(label, labels)
        self.assertEqual(self.steps(result.run_id, "check")[0]["problems"], [])

    def test_second_event_and_ceo_caller(self):
        result = self.cos.run(AGENT, "P01", "C01", inputs={"event_id": "EV114"})
        self.assertEqual(result.status, "done", result.reason)
        self.assertEqual(sorted(m["to_person_id"] for m in self.cos.outbox.messages()), ["P05", "P08"])

    def test_caller_without_access_is_refused(self):
        outsider = next(p for p in ("P03", "P04", "P05", "P06", "P08", "P09", "P10", "P30")
                        if "C02" not in self.cos.directory.client_access(p))
        result = self.cos.run(AGENT, outsider, "C02", inputs={"event_id": "EV113"})
        self.assertEqual(result.status, "refused")
        self.assertEqual(self.cos.outbox.messages(), [])

    def test_wrong_role_is_refused(self):
        self.assertEqual(self.cos.run(AGENT, "P11", "C02", inputs={"event_id": "EV113"}).status, "refused")

    def test_event_of_another_client_reads_nothing(self):
        # EV114 belongs to C01; asking for it inside C02 must not leak it.
        result = self.cos.run(AGENT, "P10", "C02", inputs={"event_id": "EV114"})
        self.assertEqual(result.status, "done")  # quiet: nothing found
        self.assertEqual(self.cos.outbox.messages(), [])
        self.assertTrue(self.steps(result.run_id, "quiet"))

    def _with_extra_question(self, cite):
        pack = self.cos.packs[AGENT]
        original = pack.parse_decision

        def parse(text):
            decision = original(text)
            decision["questions"].append({"text": "Invented question", "cites": [cite], "topic": "invented"})
            return decision
        pack.parse_decision = parse
        return self.cos.run(AGENT, "P10", "C02", inputs={"event_id": "EV113"})

    def test_fake_citation_is_stopped_by_check(self):
        result = self._with_extra_question("I99999")
        self.assertEqual(result.status, "failed")
        self.assertIn("I99999", result.reason)
        self.assertEqual(self.cos.outbox.messages(), [])
        self.assertFalse(self.steps(result.run_id, "act"))

    def test_citation_from_another_client_is_stopped(self):
        other = self.cos.memory.items("C01", kinds=["question"])[0]["item_id"]
        result = self._with_extra_question(other)
        self.assertEqual(result.status, "failed")
        self.assertEqual(self.cos.outbox.messages(), [])

    def test_citation_of_item_not_open_at_meeting_is_stopped(self):
        answered = next(i for i in self.cos.memory.items("C02", kinds=["question"])
                        if any(l["rel"] == "answers" and l["to_id"] == i["item_id"]
                               for l in self.cos.memory.scoped(["C02"]).links_of(i["item_id"])))
        result = self._with_extra_question(answered["item_id"])
        self.assertEqual(result.status, "failed")
        self.assertIn("not open", result.reason)


class MeetingPrepExamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cos = build()
        cls.result = run_exam(cls.cos)

    def test_exam_coverage_meets_threshold(self):
        r = self.result
        self.assertEqual(r["failed_runs"], [])
        self.assertGreater(r["meetings"], 40)
        # About 70% of decided topics were asked before, so 0.67 is the ceiling; 0.55 leaves room for re-decisions.
        self.assertGreaterEqual(r["mean_coverage"], 0.55)
        # Of the topics that were asked before, the brief should catch nearly all.
        self.assertGreaterEqual(r["mean_askable_coverage"], 0.85)
        self.assertGreater(r["surprise_share"], 0.2)

    def test_scores_are_saved(self):
        metrics = {s["metric"] for s in self.cos.memory.scores(exam="meeting_prep_replay")}
        self.assertEqual(metrics, {"mean_coverage", "mean_askable_coverage", "surprise_share", "injection_blocked"})

    def test_injection_is_blocked(self):
        inj = self.result["injection"]
        self.assertEqual(inj["run_status"], "done")
        self.assertEqual(inj["leaked_messages"], 0)
        self.assertTrue(inj["denial_logged"])
        self.assertTrue(self.result["injection_blocked"])


if __name__ == "__main__":
    unittest.main()
