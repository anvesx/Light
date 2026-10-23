"""Playbook writer: redaction, the section rules, the guarded run, the leak refusal and the library tools."""
import json
import tempfile
import unittest
from types import SimpleNamespace

from control_plane.company_brain import link_tools, playbook_rules
from control_plane.company_brain.agents.playbook.fake_brain import leaky_brain
from control_plane.company_brain.agents.playbook.replay_exam import judge
from control_plane.company_brain.record_sync import sync_records
from control_plane.company_brain.redaction import find_leaks, redact
from core.fake_model import FakeModel
from wiring.build_company_os import build_company_os


class RedactionCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cos = build_company_os(agents=(), state_dir=tempfile.mkdtemp())
        cls.conn = cls.cos.data_conn
        cls.addClassCleanup(cls.cos.data_conn.close)
        cls.addClassCleanup(cls.cos.memory.close)

    def test_finds_names_emails_phones_and_salary_words(self):
        self.assertEqual(find_leaks("Ask Nandini Sethi on nandini.sethi@medbridge-clinics.example or 98200 12345, salary", self.conn)[:2],
                         ["nandini.sethi@medbridge-clinics.example", "98200 12345"])
        leaks = find_leaks("MedBridge Clinics asked Meenal about the salary", self.conn)
        self.assertTrue({"MedBridge Clinics", "Meenal", "salary"} <= set(leaks))

    def test_plain_text_and_dates_are_clean(self):
        self.assertEqual(find_leaks("We need online booking. Launch on 2026-11-20 10:00, INR 4200000.", self.conn), [])

    def test_redact_removes_all_of_it(self):
        text = "Hello Sofia. We need a portal. Mail nandini.sethi@x.example or +91 98200 12345. Tailorbird wants the salary file."
        out = redact(text, self.conn)
        self.assertEqual(find_leaks(out, self.conn), [])
        self.assertTrue(out.startswith("We need a portal."))


def deal_data(stage="won"):
    item = lambda i, kind, topic, text, when, state="active": {"item_id": i, "kind": kind, "topic": topic, "text": text,
                                                              "when": when, "state": state, "answered": False}
    return {"deal": {"deal_id": "L05", "industry": "healthcare", "stage": stage}, "won_on": "2026-05-26", "last_call": "2026-08-03",
            "lost_reason": "Data storage question not answered; price too high", "project": {"start_on": "2026-06-08"}, "revenue_inr": 100,
            "items": [item("I1", "requirement", "payments", "We need payment by UPI.", "2026-05-22"),
                      item("I2", "decision", "pilot", "Let's go with a paid pilot.", "2026-05-22"),
                      item("I3", "fact", "pilot", "What went right: the pilot gave early feedback.", "2026-08-25"),
                      item("I4", "requirement", "reminders", "We need reminders on WhatsApp, not SMS.", "2026-08-11"),
                      item("I5", "blocker", "data-residency", "We are waiting for an answer on hosting.", "2026-07-30"),
                      item("I6", "sentiment", "pricing", "I was shocked to see the price.", "2026-08-01"),
                      item("I7", "requirement", "lab-integration", "We need a lab portal.", "2026-07-01"),
                      item("I8", "decision", "launch-date", "Launch on 6 November.", "2026-09-30", "superseded")]}


class RulesCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cos = build_company_os(agents=(), state_dir=tempfile.mkdtemp())
        cls.conn = cos.data_conn
        cls.addClassCleanup(cos.data_conn.close)
        cls.addClassCleanup(cos.memory.close)

    def test_won_deal_sections(self):
        plan = playbook_rules.build(deal_data(), self.conn)
        topics = lambda s: [e["topic"] for e in plan["sections"][s]]
        self.assertEqual(topics("initially_wanted"), ["payments"])
        self.assertEqual(set(topics("later_changed_to")), {"reminders", "lab-integration", "launch-date"})
        self.assertEqual(topics("went_right"), ["pilot"])
        self.assertEqual(topics("went_wrong"), [])
        self.assertNotIn("launch-date", topics("chose"))  # the superseded decision is left out
        self.assertEqual(plan["client_label"], "A healthcare client")

    def test_lost_deal_went_wrong_and_checklist(self):
        data = deal_data("lost")
        plan = playbook_rules.build(data, self.conn)
        self.assertEqual({e["topic"] for e in plan["sections"]["went_wrong"]}, {"data-residency", "pricing"})
        self.assertEqual([c["topic"] for c in plan["checklist"]], ["data-residency"])  # pricing is an objection, not a kickoff question
        self.assertEqual(plan["checklist"][0]["industries"], ["diagnostics", "healthcare"])

    def test_every_entry_cites_items_and_text_has_no_leak(self):
        plan = playbook_rules.build(deal_data(), self.conn)
        self.assertTrue(all(e["item_ids"] for v in plan["sections"].values() for e in v))
        self.assertEqual([x for t in playbook_rules.texts_of(plan) for x in find_leaks(t, self.conn)], [])


class RunCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cos = build_company_os(agents=("brain_playbook",), state_dir=tempfile.mkdtemp(),
                                   extra_backends={"sonnet-5-5": FakeModel({"brain_playbook": leaky_brain})})
        b = cls.cos.brain
        sync_records(cls.cos.data_conn, b)
        rows = [("S1", "2026-05-22T10:00", "Nandini Sethi: we need payment by UPI, mail nandini.sethi@medbridge-clinics.example", "requirement", "payments"),
                ("S2", "2026-07-14T10:00", "Please add insurance claim upload, call 98200 12345", "requirement", "insurance-claims"),
                ("S3", "2026-08-25T10:00", "What went wrong: nothing.", "fact", "pilot")]
        for ref, when, text, kind, topic in rows:
            sid = b.add_source("C04", "fathom", ref, text, origin_ref=ref, occurred_at=when, participants=[], language="en",
                               lines=[{"line_no": 1, "speaker": "A", "text": text}])
            b.add_brain_item("C04", kind, text, topic=topic, source_id=sid, line_from=1, line_to=1, quote_raw=text, quote_clean=text,
                             confidence=0.9)

    @classmethod
    def tearDownClass(cls):
        for part in (cls.cos.data_conn, cls.cos.memory, cls.cos.outbox, cls.cos.approvals):
            part.close()

    def run_deal(self, deal_id="L05", area="C04", model="fake"):
        return self.cos.run("brain_playbook", "system", area, trigger_kind="event", model=model, inputs={"deal_id": deal_id})

    def test_clean_run_publishes_a_redacted_playbook_and_checklist(self):
        r = self.run_deal()
        self.assertEqual(r.status, "done", r.reason)
        pb = next(p for p in self.cos.brain.playbooks() if p["deal_id"] == "L05")
        blob = json.dumps(pb) + json.dumps(self.cos.brain.checklist())
        self.assertEqual(find_leaks(blob, self.cos.data_conn), [])
        self.assertIn("insurance-claims", {e["topic"] for e in pb["sections"]["later_changed_to"]})
        self.assertTrue(any(c["topic"] == "insurance-claims" for c in self.cos.brain.checklist()))
        self.assertEqual(pb["revenue_inr"], 5650000)

    def test_a_draft_with_a_leak_is_refused_and_nothing_is_saved(self):
        before = self.cos.brain.playbooks()
        r = self.run_deal(model="sonnet-5-5")
        self.assertEqual(r.status, "failed")
        self.assertIn("leaks private details", r.reason)
        self.assertEqual(self.cos.brain.playbooks(), before)

    def test_an_open_deal_gets_no_playbook(self):
        r = self.run_deal("L20", "C07")
        self.assertEqual(r.status, "done")
        self.assertEqual(r.final_text, "quiet")
        self.assertFalse([p for p in self.cos.brain.playbooks() if p["deal_id"] == "L20"])

    def test_publish_tool_refuses_open_deals_and_foreign_items(self):
        ctx = SimpleNamespace(task=SimpleNamespace(area_id="C07"), run_id="R")
        sections = {s: [] for s in playbook_rules.SECTIONS}
        reply = json.loads(link_tools.make_publish_playbook(self.cos.brain).fn(
            {"deal_id": "L20", "sections": sections, "tags": [], "client_label": "x"}, ctx))
        self.assertIn("won or lost", reply["error"])
        ctx = SimpleNamespace(task=SimpleNamespace(area_id="C04"), run_id="R")
        other = self.cos.brain.brain_items(["C04"])[0]["item_id"]
        ctx.task.area_id = "C01"
        sections["chose"] = [{"text": "x", "topic": "pilot", "item_ids": [other]}]
        reply = json.loads(link_tools.make_publish_playbook(self.cos.brain).fn(
            {"deal_id": "L01", "sections": sections, "tags": [], "client_label": "x"}, ctx))
        self.assertIn("not in area", reply["error"])

    def test_judge(self):
        row = {"status": "done", "missing_topics": [], "foreign_entries": 0}
        good = {"playbooks": 4, "expected": 4, "rows": [row], "leaks": 0, "leak_blocked": True}
        self.assertTrue(judge(good)[2])
        self.assertFalse(judge({**good, "leaks": 1})[2])
        self.assertFalse(judge({**good, "leak_blocked": False})[2])


if __name__ == "__main__":
    unittest.main()
