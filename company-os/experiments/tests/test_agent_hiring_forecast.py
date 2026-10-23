"""Tests for the hiring forecast agent: a real run, a refusal, a wrong number, a short team and the exam."""
import json
import os
import re
import shutil
import tempfile
import unittest
from dataclasses import replace

from agents.hiring_forecast.fake_brain import brain
from agents.hiring_forecast.replay_exam import derive_key, run_exam
from company_data import DB_PATH, connect
from wiring.build_company_os import build_company_os

AREA = "devx-internal"
AS_OF = {"as_of": "2026-10-19"}


class HiringForecastTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.cos = build_company_os(agents=("hiring_forecast",), state_dir=self._dir.name)

    def steps(self, result):
        return [s["step"] for s in self.cos.memory.run_steps(result.run_id)]

    def test_hr_run_tells_hr_and_ceo_with_numbers_and_assumptions(self):
        r = self.cos.run("hiring_forecast", "P90", AREA, inputs=AS_OF)
        self.assertEqual(r.status, "done")
        steps = self.steps(r)
        if "quiet" in steps:
            self.assertEqual(r.reason, "quiet")
            return
        for who in ("P90", "P01"):
            msgs = self.cos.outbox.messages(who)
            self.assertEqual(len(msgs), 1)
            self.assertEqual((msgs[0]["kind"], msgs[0]["agent"]), ("forecast", "hiring_forecast"))
            text = msgs[0]["text"]
            self.assertIn("engineering", text)
            self.assertIn("design", text)
            self.assertRegex(text, r"\d+\.\d hours a week")
            self.assertIn("Assumptions:", text)
            self.assertIn("80%", text)
            self.assertIn("4 weeks", text)
        for step in ("record", "understand", "decide", "check", "act", "remember"):
            self.assertIn(step, steps)
        logged = [s["detail"].get("name") for s in self.cos.memory.run_steps(r.run_id) if s["step"] == "tool"]
        for tool in ("team_capacity_and_load", "pipeline_demand", "remaining_sow_hours", "send_private_message"):
            self.assertIn(tool, logged)
        self.assertTrue(self.cos.memory.cases(area_id=AREA, agent="hiring_forecast"))

    def test_engineer_is_refused(self):
        r = self.cos.run("hiring_forecast", "P12", AREA, inputs=AS_OF)
        self.assertEqual(r.status, "refused")
        self.assertEqual(self.cos.ledger.entries, [])
        self.assertEqual(self.cos.outbox.messages(), [])

    def test_no_message_has_a_person_id_or_a_salary(self):
        self.cos.run("hiring_forecast", "P90", AREA, inputs=AS_OF)
        for m in self.cos.outbox.messages():
            self.assertIsNone(re.search(r"\bP\d{2,3}\b", m["text"]))
            self.assertIsNone(re.search(r"salar|\bctc\b|\bpay\b", m["text"], re.I))

    def test_forecast_with_a_wrong_number_is_stopped_by_check(self):
        def wrong(request):
            reply = brain(request)
            data = json.loads(reply.text)
            row = (data["short_teams"] or data["spare_teams"])[0]
            row["why"] = re.sub(r"\d+\.\d", "7777.7", row["why"], count=1)
            return replace(reply, text=json.dumps(data))
        self.cos.gateway._backends["fake"].brains["hiring_forecast"] = wrong
        r = self.cos.run("hiring_forecast", "P90", AREA, inputs=AS_OF)
        self.assertEqual(r.status, "failed")
        self.assertIn("7777.7", r.reason)
        self.assertEqual(self.cos.outbox.messages(), [])

    def test_text_with_a_person_id_is_stopped_by_check(self):
        def leaky(request):
            reply = brain(request)
            data = json.loads(reply.text)
            data["summary"] += " Ask P12 about it."
            return replace(reply, text=json.dumps(data))
        self.cos.gateway._backends["fake"].brains["hiring_forecast"] = leaky
        r = self.cos.run("hiring_forecast", "P90", AREA, inputs=AS_OF)
        self.assertEqual(r.status, "failed")
        self.assertIn("person id", r.reason)

    def test_exam_agrees_with_the_derived_key(self):
        out = run_exam(self.cos)
        self.assertTrue(out["agreed"], out)
        self.assertGreaterEqual(out["checked"], 1)
        self.assertEqual(out["disagree"], 0)
        self.assertTrue(self.cos.memory.scores(exam="hiring_forecast_exam", agent="hiring_forecast"))


class BigWonDealTests(unittest.TestCase):
    """A big deal won last week makes engineering short. Uses a copy of the data, never the shared file."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        db = os.path.join(self._dir.name, "data.db")
        shutil.copy(DB_PATH, db)
        conn = connect(db)
        conn.execute("INSERT INTO leads VALUES ('L99', 'C02', 'expansion', 'P04', 'won', '2026-10-05', '2026-10-14', 10000000)")
        conn.commit()
        conn.close()
        self.cos = build_company_os(agents=("hiring_forecast",), state_dir=self._dir.name, data_db=db)

    def test_short_team_gets_a_week_and_a_hiring_start(self):
        r = self.cos.run("hiring_forecast", "P90", AREA, inputs=AS_OF)
        self.assertEqual(r.status, "done", r.reason)
        key = derive_key(self.cos.data_conn)
        self.assertIn("engineering", key["short"])
        text = self.cos.outbox.messages("P01")[0]["text"]
        self.assertIn("[SHORT] engineering", text)
        self.assertIn(f"starting the week of {key['short']['engineering']['starts_week']}", text)
        self.assertIn(f"Start hiring now (the plan date {key['short']['engineering']['hire_by']} has passed)", text)

    def test_exam_agrees_on_the_short_team(self):
        out = run_exam(self.cos)
        self.assertTrue(out["agreed"], out)
        self.assertIn("engineering", out["pack_short"])


if __name__ == "__main__":
    unittest.main()
