"""Tests for the project risk agent: a real flag, a quiet run, a refusal, a bad brief and the replay exam."""
import json
import re
import tempfile
import unittest
from dataclasses import replace

from agents.project_risk.fake_brain import brain
from agents.project_risk.replay_exam import run_exam
from wiring.build_company_os import build_company_os

AS_OF = {"as_of": "2026-10-19"}


class ProjectRiskTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.cos = build_company_os(agents=("project_risk",), state_dir=self._dir.name)

    def steps(self, result):
        return [s["step"] for s in self.cos.memory.run_steps(result.run_id)]

    def test_over_sow_client_flags_the_csm_with_real_numbers(self):
        r = self.cos.run("project_risk", "P06", "C02", inputs=AS_OF)
        self.assertIn(r.status, ("held", "done"))
        msgs = self.cos.outbox.messages("P06")
        self.assertEqual(len(msgs), 1)
        self.assertEqual((msgs[0]["kind"], msgs[0]["agent"]), ("flag", "project_risk"))
        self.assertIn("PR03", msgs[0]["text"])
        overview = json.loads(self.cos.runtime.registry.get("project_overview").fn({}, _Ctx("C02")))["projects"][0]
        self.assertIn(str(overview["hours_logged"]), msgs[0]["text"])
        self.assertIn(str(overview["logged_pct_of_estimate"]), msgs[0]["text"])
        self.assertEqual(self.cos.outbox.messages("P05"), [])
        pending = self.cos.approvals.pending()
        self.assertEqual([p["tool"] for p in pending], ["create_followup_task"])
        self.assertEqual(r.status, "held")
        self.assertEqual([i for i in self.cos.memory.items("C02", kinds=["task"]) if i["source"] == "agent:project_risk"], [])
        steps = self.steps(r)
        for step in ("record", "understand", "decide", "check", "act", "remember"):
            self.assertIn(step, steps)
        logged = [s["detail"].get("name") for s in self.cos.memory.run_steps(r.run_id) if s["step"] == "tool"]
        for tool in ("project_overview", "client_channel_activity", "weekly_hours_by_person", "send_private_message",
                     "create_followup_task"):
            self.assertIn(tool, logged)
        self.assertTrue(self.cos.memory.cases(area_id="C02", agent="project_risk"))

    def test_healthy_client_is_quiet_without_a_model_call(self):
        r = self.cos.run("project_risk", "P06", "C05", inputs=AS_OF)
        self.assertEqual(r.status, "done")
        self.assertEqual(self.cos.ledger.entries, [])
        self.assertIn("quiet", self.steps(r))
        self.assertEqual(self.cos.outbox.messages(), [])

    def test_engineer_is_refused(self):
        r = self.cos.run("project_risk", "P12", "C01", inputs=AS_OF)
        self.assertEqual(r.status, "refused")
        self.assertEqual(self.cos.ledger.entries, [])
        self.assertEqual(self.cos.outbox.messages(), [])

    def test_brief_with_a_wrong_number_is_stopped_by_check(self):
        def wrong(request):
            reply = brain(request)
            data = json.loads(reply.text)
            data["flags"][0]["evidence"] = re.sub(r"\d+", "7777", data["flags"][0]["evidence"], count=1)
            return replace(reply, text=json.dumps(data))
        self.cos.gateway._backends["fake"].brains["project_risk"] = wrong
        r = self.cos.run("project_risk", "P06", "C02", inputs=AS_OF)
        self.assertEqual(r.status, "failed")
        self.assertIn("7777", r.reason)
        self.assertEqual(self.cos.outbox.messages(), [])
        self.assertEqual(self.cos.approvals.pending(), [])

    def test_exam_finds_all_cases_and_no_look_alikes(self):
        out = run_exam(self.cos)
        self.assertEqual((out["planted"], out["found"], out["missed"]), (4, 4, 0))
        self.assertEqual(out["false_alarms"], 0)
        self.assertLessEqual(out["max_lag_days"], 3)
        self.assertTrue(self.cos.memory.scores(exam="project_risk_replay", agent="project_risk"))


class _Ctx:
    """Just enough run context to call a read tool directly."""
    def __init__(self, area_id):
        from contract.types import Task
        self.task = Task(agent="project_risk", caller_id="P06", area_id=area_id, trigger_kind="test", inputs=AS_OF)


if __name__ == "__main__":
    unittest.main()
