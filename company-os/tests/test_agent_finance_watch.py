"""Tests for the finance watch agent pack: a real run, the refusals, the salary rule, the check step and the exam."""
import json
import shutil
import tempfile
import unittest

from agents.finance.watch import replay_exam
from contract.types import ModelReply
from wiring.build_company_os import build_company_os

DUP_DATE = "2026-09-25"   # INV051 and INV054 from SkyWay Travel Desk; INV054 is unpaid


class FinanceWatchTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fw_test_")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.cos = build_company_os(agents=("finance_watch",), state_dir=self.dir)
        self.addCleanup(self.cos.data_conn.close)

    def run_as(self, caller, as_of=DUP_DATE):
        return self.cos.run("finance_watch", caller, "devx-internal", inputs={"as_of": as_of})

    def steps(self, result):
        return self.cos.memory.run_steps(result.run_id)

    def test_duplicate_invoice_run_by_finance_lead(self):
        result = self.run_as("P07")
        self.assertEqual(result.status, "held")
        mine = self.cos.outbox.messages("P07")
        self.assertEqual(len(mine), 1)
        self.assertIn("INV051", mine[0]["text"])
        self.assertIn("INV054", mine[0]["text"])
        self.assertIn("Next step", mine[0]["text"])
        ceo = self.cos.outbox.messages("P01")   # the ongoing travel finding goes to the CEO, alone
        self.assertTrue(all("INV051" not in m["text"] for m in ceo))
        pending = self.cos.approvals.pending()
        self.assertTrue(any(a["tool"] == "create_followup_task" and "INV054" in json.dumps(a["args"])
                            for a in pending))
        tasks = self.cos.memory.items("devx-internal", kinds=["task"])
        self.assertFalse([t for t in tasks if t["source"] == "agent:finance_watch"])   # held, not run
        names = [(s["detail"].get("name"), s["detail"].get("verdict")) for s in self.steps(result) if s["step"] == "tool"]
        for tool in ("invoices_window", "payments_window", "budget_vs_spend", "travel_share_of_salary",
                     "send_private_message"):
            self.assertIn((tool, "allow"), names)
        self.assertIn(("create_followup_task", "ask"), names)
        labels = [s["step"] for s in self.steps(result)]
        for step in ("record", "understand", "decide", "check", "act", "remember"):
            self.assertIn(step, labels)
        self.assertTrue(self.cos.memory.cases(agent="finance_watch"))

    def test_travel_finding_also_goes_to_the_ceo(self):
        self.run_as("P07", "2026-09-14")
        ceo = self.cos.outbox.messages("P01")
        self.assertEqual(len(ceo), 1)
        self.assertIn("travel share of salary", ceo[0]["text"])
        self.assertNotIn("duplicate", ceo[0]["text"])

    def test_quiet_day_makes_no_message_and_no_model_call(self):
        result = self.cos.run("finance_watch", "system", "devx-internal", trigger_kind="timer",
                              inputs={"as_of": "2026-05-02"})
        self.assertEqual(result.status, "done")
        self.assertEqual(self.cos.outbox.messages(), [])
        self.assertIn("quiet", [s["step"] for s in self.steps(result)])
        self.assertFalse([s for s in self.steps(result) if s["step"] == "model_call"])

    def test_engineer_is_refused(self):
        result = self.run_as("P11")
        self.assertEqual(result.status, "refused")
        self.assertEqual(self.cos.outbox.messages(), [])

    def test_no_message_shows_one_persons_salary(self):
        for as_of in ("2026-09-14", "2026-09-18", DUP_DATE, "2026-08-19"):
            self.run_as("P07", as_of)
        salaries = {str(r[0]) for r in self.cos.data_conn.execute("SELECT monthly_salary_inr FROM people")}
        texts = [m["text"].replace(",", "") for m in self.cos.outbox.messages()]
        self.assertTrue(texts)
        for text in texts:
            for salary in salaries:
                self.assertNotRegex(text, rf"(?<!\d){salary}(?!\d)")
        self.assertTrue(all("salary" not in a["args"].get("title", "") for a in self.cos.approvals.pending()))

    def test_wrong_amount_is_stopped_by_check(self):
        brains = self.cos.gateway._backends["fake"].brains
        real = brains["finance_watch"]

        def wrong(request):
            data = json.loads(real(request).text)
            data["findings"][0]["amount_inr"] += 1
            return ModelReply(text=json.dumps(data))
        brains["finance_watch"] = wrong
        result = self.run_as("P07")
        self.assertEqual(result.status, "failed")
        self.assertIn("does not match", result.reason)
        self.assertEqual(self.cos.outbox.messages(), [])
        self.assertEqual(self.cos.approvals.pending(), [])

    def test_a_single_salary_in_the_text_is_stopped_by_check(self):
        salary = self.cos.data_conn.execute(
            "SELECT monthly_salary_inr FROM people WHERE role = 'finance_lead'").fetchone()[0]
        brains = self.cos.gateway._backends["fake"].brains
        real = brains["finance_watch"]

        def leaky(request):
            data = json.loads(real(request).text)
            data["findings"][0]["evidence"] += f" The approver earns {salary:,} a month."
            return ModelReply(text=json.dumps(data))
        brains["finance_watch"] = leaky
        result = self.run_as("P07")
        self.assertEqual(result.status, "failed")
        self.assertIn("salary", result.reason)
        self.assertEqual(self.cos.outbox.messages(), [])

    def test_exam_finds_every_case_and_flags_no_look_alike(self):
        report = replay_exam.run_exam(self.cos)
        self.assertEqual(report["missed_ids"], [])
        self.assertEqual(report["found"], 8)
        self.assertEqual(report["false_alarms"], 0)
        scores = {s["metric"]: s["value"] for s in self.cos.memory.scores(agent="finance_watch")}
        self.assertEqual(scores["found"], 8)
        self.assertEqual(scores["false_alarms"], 0)


if __name__ == "__main__":
    unittest.main()
