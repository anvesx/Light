"""Tests for the store watch agent pack (fraud_watch)."""
import shutil
import tempfile
import unittest
from dataclasses import replace

from agents.fraud_watch import fake_brain
from agents.fraud_watch.pattern_rules import BANNED
from agents.fraud_watch.replay_exam import run_exam
from wiring.build_company_os import build_company_os

AS_OF = "2026-10-02"
CSM = "P05"


class FraudWatchCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fraud_watch_test_")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.cos = build_company_os(agents=("fraud_watch",), state_dir=self.dir)

    def run_agent(self, caller=CSM, area="C01", as_of=AS_OF):
        return self.cos.run("fraud_watch", caller, area, inputs={"as_of": as_of})

    def steps(self, result):
        return [s["step"] for s in self.cos.memory.run_steps(result.run_id)]


class RunTests(FraudWatchCase):
    def test_message_goes_to_csm_with_evidence(self):
        r = self.run_agent()
        msgs = self.cos.outbox.messages(CSM)
        self.assertEqual(len(msgs), 1)
        text = msgs[0]["text"]
        for staff in ("S09", "S13", "S05"):
            self.assertIn(staff, text)
        self.assertIn("unusual pattern", text.lower())
        self.assertIsNone(BANNED.search(text))
        self.assertEqual(msgs[0]["agent"], "fraud_watch")
        self.assertEqual(self.cos.outbox.messages("S01"), [])
        self.assertEqual(r.status, "held")

    def test_followup_is_held_not_created(self):
        self.run_agent()
        pending = self.cos.approvals.pending()
        self.assertTrue(pending)
        made = [i for i in self.cos.memory.items("C01", kinds=["task"]) if i["source"] == "agent:fraud_watch"]
        self.assertEqual(made, [])

    def test_every_read_and_action_is_in_the_steps(self):
        r = self.run_agent()
        steps = self.cos.memory.run_steps(r.run_id)
        tools = [s["detail"]["name"] for s in steps if s["step"] == "tool"]
        for name in ("refunds_by_staff", "discounts_by_staff", "remakes_by_staff", "send_private_message",
                     "create_followup_task"):
            self.assertIn(name, tools)
        self.assertLess(self.steps(r).index("check"), self.steps(r).index("act"))
        self.assertEqual(len(self.cos.memory.cases("C01", agent="fraud_watch")), 3)

    def test_quiet_when_nothing_is_unusual(self):
        r = self.run_agent(as_of="2026-07-01")
        self.assertEqual(r.status, "done")
        self.assertIn("quiet", self.steps(r))
        self.assertEqual(self.cos.outbox.messages(), [])

    def test_csm_of_another_client_is_refused(self):
        r = self.run_agent(caller="P06")
        self.assertEqual(r.status, "refused")
        self.assertEqual(self.cos.outbox.messages(), [])

    def test_wrong_area_is_refused(self):
        self.assertEqual(self.run_agent(area="C02").status, "refused")


class CheckTests(FraudWatchCase):
    def run_with_brain(self, change):
        original = fake_brain.brain

        def variant(req):
            reply = original(req)
            return replace(reply, text=change(reply.text))
        self.cos.gateway._backends["fake"].brains["fraud_watch"] = variant
        return self.run_agent()

    def test_banned_word_is_stopped(self):
        for word in ("fraud", "theft", "stealing", "cheating"):
            r = self.run_with_brain(lambda t, w=word: t.replace("worth a second look", f"possible {w}"))
            self.assertEqual(r.status, "failed", word)
            self.assertIn("banned words", r.reason)
        self.assertEqual(self.cos.outbox.messages(), [])

    def test_made_up_number_is_stopped(self):
        r = self.run_with_brain(lambda t: t.replace("Window:", "and 99 more. Window:"))
        self.assertEqual(r.status, "failed")
        self.assertIn("not in the data", r.reason)

    def test_unknown_staff_is_stopped(self):
        r = self.run_with_brain(lambda t: t.replace('"S09"', '"S04"', 1))
        self.assertEqual(r.status, "failed")
        self.assertEqual(self.cos.outbox.messages(), [])

    def test_wrong_recipient_is_stopped(self):
        r = self.run_with_brain(lambda t: t[:-1] + ', "to": "S01"}')
        self.assertEqual(r.status, "failed")
        self.assertIn("recipient", r.reason)


class ExamTests(FraudWatchCase):
    def test_exam_finds_cases_and_skips_look_alikes(self):
        result = run_exam(self.cos)
        self.assertTrue(all(c["found"] for c in result["cases"]))
        self.assertEqual([c["case_id"] for c in result["cases"]], ["FRD-1", "FRD-2", "FRD-3"])
        self.assertFalse(any(la["flagged"] for la in result["look_alikes"]))
        self.assertEqual((result["found"], result["missed"], result["false_alarms"]), (3, 0, 0))
        names = {s["metric"] for s in self.cos.memory.scores("replay", "fraud_watch")}
        self.assertEqual(names, {"found", "missed", "false_alarms"})


if __name__ == "__main__":
    unittest.main()
