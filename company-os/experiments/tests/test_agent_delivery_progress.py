"""Tests for the delivery progress agent: flags, snapshots, an event run, refusals, wording rules and the exam."""
import json
import re
import tempfile
import unittest
from dataclasses import replace

from agents.delivery_progress.fake_brain import brain
from agents.delivery_progress.replay_exam import run_exam
from wiring.build_company_os import build_company_os

AS_OF = {"as_of": "2026-10-19"}


class DeliveryProgressTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.cos = build_company_os(agents=("delivery_progress",), state_dir=self._dir.name)

    def snapshots(self, area):
        return [json.loads(i["text"]) for i in self.cos.memory.items(area, kinds=["progress_snapshot"])]

    def test_unbilled_work_goes_to_the_projects_csm_and_a_snapshot_is_written(self):
        r = self.cos.run("delivery_progress", "P05", "C01", inputs=AS_OF)
        self.assertEqual(r.status, "done")
        msgs = self.cos.outbox.messages("P05")
        self.assertEqual(len(msgs), 1)
        self.assertEqual((msgs[0]["kind"], msgs[0]["agent"]), ("flag", "delivery_progress"))
        self.assertIn("PR02", msgs[0]["text"])
        self.assertIn("6 things were built that are not in the signed scope", msgs[0]["text"])
        # CSMs read business words only: no PR names, merges or code prefixes.
        import re
        self.assertIsNone(re.search(r"\bPRs?\b|pull request|\bmerged?\b|\b(feat|fix|chore):", msgs[0]["text"].split("\n", 2)[2]))
        self.assertEqual(self.cos.outbox.messages("P06"), [])
        snaps = {s["project_id"]: s for s in self.snapshots("C01")}
        self.assertEqual(set(snaps), {"PR01", "PR02"})
        snap = snaps["PR02"]
        self.assertEqual((snap["as_of"], snap["client_id"], snap["csm_id"]), ("2026-10-19", "C01", "P05"))
        self.assertEqual(snap["unbilled_prs"], 6)
        self.assertEqual([f["signal"] for f in snap["flags"]], ["unbilled_work"])
        self.assertEqual(snaps["PR01"]["flags"], [])
        self.assertTrue(snap["headline"])
        self.assertEqual(len(snap["scope"]), snap["scope_counts"]["total"])
        item = self.cos.memory.items("C01", kinds=["progress_snapshot"])[0]
        self.assertEqual((item["source"], item["created_at"]), ("delivery_progress", "2026-10-19"))
        cases = self.cos.memory.cases(area_id="C01", agent="delivery_progress")
        self.assertEqual([c["subject"] for c in cases], ["unbilled_work:PR02"])

    def test_all_three_signal_kinds_reach_their_csm(self):
        for client, csm in (("C03", "P06"), ("C04", "P05")):
            self.cos.run("delivery_progress", "system", client, trigger_kind="timer", inputs=AS_OF)
        self.assertIn("changed 5 times", self.cos.outbox.messages("P06")[0]["text"])
        text = self.cos.outbox.messages("P05")[0]["text"]
        self.assertIn("2027-11-13", text)
        self.assertIn("57.6%", text)
        self.assertEqual({s["project_id"]: s["status"] for s in self.snapshots("C04")}, {"PR05": "behind"})

    def test_on_track_client_gets_a_snapshot_and_no_message(self):
        self.cos.run("delivery_progress", "P06", "C05", inputs=AS_OF)
        self.assertEqual(self.cos.outbox.messages(), [])
        self.assertEqual([s["status"] for s in self.snapshots("C05")], ["on track"])

    def test_same_flag_is_not_sent_twice_in_a_week(self):
        self.cos.run("delivery_progress", "system", "C01", trigger_kind="timer", inputs=AS_OF)
        self.cos.run("delivery_progress", "system", "C01", trigger_kind="timer", inputs={"as_of": "2026-10-20"})
        self.assertEqual(len(self.cos.outbox.messages("P05")), 1)
        self.assertEqual(len(self.snapshots("C01")), 4)

    def test_pr_merge_event_run_updates_that_project(self):
        pr = self.cos.data_conn.execute(
            "SELECT pr_id FROM pull_requests WHERE project_id = 'PR02' AND task_id IS NULL ORDER BY pr_id LIMIT 1"
        ).fetchone()[0]
        r = self.cos.run("delivery_progress", "system", "C01", trigger_kind="event", inputs={"pr_id": pr, **AS_OF})
        self.assertEqual(r.status, "done")
        snaps = self.snapshots("C01")
        self.assertEqual([(s["project_id"], s["trigger_pr_id"]) for s in snaps], [("PR02", pr)])
        self.assertEqual(len(self.cos.outbox.messages("P05")), 1)
        self.assertEqual(self.cos.memory.runs("delivery_progress")[0]["trigger_kind"], "event")

    def test_engineer_is_refused(self):
        r = self.cos.run("delivery_progress", "P12", "C01", inputs=AS_OF)
        self.assertEqual(r.status, "refused")
        self.assertEqual(self.cos.ledger.entries, [])
        self.assertEqual((self.cos.outbox.messages(), self.snapshots("C01")), ([], []))

    def test_no_developer_is_named_or_counted(self):
        for client in ("C01", "C02", "C03", "C04", "C05"):
            self.cos.run("delivery_progress", "system", client, trigger_kind="timer", inputs=AS_OF)
        conn = self.cos.data_conn
        names = [r[0] for r in conn.execute("SELECT name FROM people WHERE role IN ('engineer', 'designer')")]
        ids = {r[0] for r in conn.execute("SELECT person_id FROM people WHERE role IN ('engineer', 'designer')")}
        texts = [m["text"] for m in self.cos.outbox.messages()]
        texts += [i["text"] for i in self.cos.memory.items(kinds=["progress_snapshot"])]
        self.assertTrue(texts)
        for text in texts:
            for name in names:
                self.assertNotIn(name, text)
            self.assertFalse(ids & set(re.findall(r"\b[PXS]\d{2,3}\b", text)))
            self.assertNotRegex(text.lower(), r"per (developer|engineer|person)|by (developer|engineer)|lines")

    def test_brief_with_a_wrong_number_is_stopped_by_check(self):
        def wrong(request):
            reply = brain(request)
            data = json.loads(reply.text)
            data["flags"][0]["evidence"] = re.sub(r"\d+", "7777", data["flags"][0]["evidence"], count=1)
            return replace(reply, text=json.dumps(data))
        self.cos.gateway._backends["fake"].brains["delivery_progress"] = wrong
        r = self.cos.run("delivery_progress", "P05", "C01", inputs=AS_OF)
        self.assertEqual(r.status, "failed")
        self.assertIn("7777", r.reason)
        self.assertEqual((self.cos.outbox.messages(), self.snapshots("C01")), ([], []))

    def test_brief_that_names_a_developer_is_stopped_by_check(self):
        def names(request):
            reply = brain(request)
            data = json.loads(reply.text)
            data["flags"][0]["why_it_matters"] = "Arjun Singh built most of it."
            return replace(reply, text=json.dumps(data))
        self.cos.gateway._backends["fake"].brains["delivery_progress"] = names
        r = self.cos.run("delivery_progress", "P05", "C01", inputs=AS_OF)
        self.assertEqual(r.status, "failed")
        self.assertIn("names a person", r.reason)

    def test_exam_finds_all_cases_and_no_look_alikes(self):
        out = run_exam(self.cos)
        self.assertEqual((out["planted"], out["found"], out["missed"]), (3, 3, 0))
        self.assertEqual(out["false_alarms"], 0)
        self.assertGreaterEqual(out["min_lag_days"], 0)
        self.assertEqual(out["other_flags"], [])
        self.assertTrue(self.cos.memory.scores(exam="delivery_progress_replay", agent="delivery_progress"))


if __name__ == "__main__":
    unittest.main()
