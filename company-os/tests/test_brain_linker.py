"""Linker: the link rules, the guarded run on a small brain, and the area limit of its tools."""
import json
import tempfile
import unittest
from types import SimpleNamespace

from control_plane.company_brain import link_rules
from control_plane.company_brain.agents.linker.replay_exam import judge
from control_plane.company_brain.record_sync import sync_records
from wiring.build_company_os import build_company_os


def item(item_id, kind, topic, text, when="2026-09-01", line=1, source="S1", **extra):
    return {"item_id": item_id, "kind": kind, "topic": topic, "text": text, "when": when, "line_from": line, "line_to": line,
            "source_id": source, "project_id": None, "deal_id": None, **extra}


class RulesCase(unittest.TestCase):
    def plan(self, new, others=()):
        return link_rules.plan_links(list(new), list(others), set())["links"]

    def rels(self, links):
        return {(l["from"], l["rel"], l["to"]) for l in links}

    def test_newer_decision_with_a_different_date_supersedes(self):
        old = item("A", "decision", "launch-date", "We decided the launch is on 6 November.", when="2026-09-30", source="S1")
        new = item("B", "decision", "launch-date", "We decided the launch will be on 20 November.", when="2026-10-10", source="S2")
        self.assertEqual(self.rels(self.plan([new], [old])), {("B", "supersedes", "A")})

    def test_the_word_decided_is_not_the_month_dec(self):
        self.assertEqual(link_rules.quantities("We decided to go with DevX"), set())

    def test_decision_without_a_value_does_not_supersede(self):
        old = item("A", "decision", "pilot", "Let's go with a paid pilot in one clinic first.", source="S1")
        new = item("B", "decision", "pilot", "We decided to go with DevX for the pilot.", when="2026-09-02", source="S2")
        self.assertEqual([l for l in self.plan([new], [old]) if l["rel"] == "supersedes"], [])

    def test_two_facts_with_different_amounts_contradict(self):
        old = item("A", "money", "budget", "We have kept the budget at INR 14 lakh.", source="S1")
        new = item("B", "money", "budget", "The budget is INR 18 lakh for the first release.", when="2026-09-02", source="S2")
        self.assertEqual(self.rels(self.plan([new], [old])), {("B", "contradicts", "A")})

    def test_repeat_is_same_as(self):
        old = item("A", "requirement", "inventory-sync", "And we need the stock of every shop to update together.", source="S1")
        new = item("B", "requirement", "inventory-sync", "We need the stock of every shop to update together.", when="2026-09-02", source="S2")
        self.assertEqual(self.rels(self.plan([new], [old])), {("B", "same_as", "A")})

    def test_question_is_answered_by_the_decision_a_few_lines_later(self):
        q = item("Q", "question", "reminders", "And what do we do about reminders, which channel?", line=6)
        fact = item("F", "fact", "reminders", "Meaning patients use WhatsApp more.", line=7)
        dec = item("D", "decision", "reminders", "We decided: the reminders will go by WhatsApp only.", line=9)
        self.assertEqual(self.rels(self.plan([q, fact, dec])), {("D", "answers", "Q")})

    def test_blocker_follows_up_the_latest_decision(self):
        dec = item("D", "decision", "reminders", "We decided: the reminders will go by WhatsApp only.", source="S1")
        blocker = item("B", "blocker", "reminders", "The WhatsApp approval has not come yet.", when="2026-10-10", source="S2")
        self.assertEqual(self.rels(self.plan([blocker], [dec])), {("B", "follows_up", "D")})

    def test_items_of_different_projects_never_link(self):
        a = item("A", "money", "budget", "Budget is INR 14 lakh.", project_id="PR01")
        b = item("B", "money", "budget", "Budget is INR 18 lakh.", when="2026-09-02", source="S2", project_id="PR02")
        self.assertEqual(self.plan([b], [a]), [])

    def test_scope_uses_the_only_project_or_a_name_in_the_title(self):
        projects = [{"project_id": "PR01", "name": "POS Rollout"}, {"project_id": "PR02", "name": "Ecommerce Revamp"}]
        source = {"title": "Ecommerce Revamp sync", "project_id": None, "deal_id": None}
        self.assertEqual(link_rules.scope_for(source, {"text": "x"}, projects, [{"deal_id": "L01"}, {"deal_id": "L02"}]), ("PR02", None))
        self.assertEqual(link_rules.scope_for({"title": "t"}, {"text": "x"}, projects[:1], [{"deal_id": "L20"}]), ("PR01", "L20"))


class RunCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.cos = build_company_os(agents=("brain_linker",), state_dir=cls.tmp.name)
        sync_records(cls.cos.data_conn, cls.cos.brain)

    @classmethod
    def tearDownClass(cls):
        for part in (cls.cos.data_conn, cls.cos.memory, cls.cos.outbox, cls.cos.approvals):
            part.close()
        cls.tmp.cleanup()

    def source(self, area, ref, when, texts, kinds):
        b = self.cos.brain
        lines = [{"line_no": n, "speaker": "A", "text": t} for n, t in enumerate(texts, 1)]
        sid = b.add_source(area, "fathom", f"{ref} call", "\n".join(texts), origin_ref=ref, occurred_at=when, participants=[],
                           language="en", lines=lines)
        ids = [b.add_brain_item(area, k, t, topic=tp, source_id=sid, line_from=n, line_to=n, quote_raw=t, quote_clean=t,
                                confidence=0.9) for n, (t, (k, tp)) in enumerate(zip(texts, kinds), 1)]
        return sid, ids

    def run_linker(self, area, sid):
        return self.cos.run("brain_linker", "system", area, trigger_kind="event", inputs={"source_id": sid})

    def test_run_supersedes_older_decision_and_sets_the_deal(self):
        _, (old,) = self.source("C07", "T1", "2026-09-01T10:00", ["We decided the launch is on 6 November."], [("decision", "launch-date")])
        sid, (new,) = self.source("C07", "T2", "2026-10-10T10:00", ["We decided the launch will be on 20 November."], [("decision", "launch-date")])
        self.assertEqual(self.run_linker("C07", sid).status, "done")  # first run covers T1 too when T2 is linked
        b = self.cos.brain
        self.assertEqual(b.get_brain_item(old)["state"], "superseded")
        self.assertEqual(b.get_brain_item(new)["state"], "active")
        self.assertIn((new, "supersedes", old), {(l["from_id"], l["rel"], l["to_id"]) for l in b.memory.links_of(new)})
        self.assertEqual(b.get_brain_item(new)["facts"]["deal_id"], "L20")  # the only deal in C07

    def test_contradiction_resolves_by_itself_with_a_check_row(self):
        _, (old,) = self.source("C08", "T3", "2026-10-06T10:00", ["We have kept the budget at INR 14 lakh, not more."], [("money", "budget")])
        sid, (new,) = self.source("C08", "T4", "2026-10-07T10:00", ["The budget is INR 18 lakh for the first release."], [("money", "budget")])
        self.assertEqual(self.run_linker("C08", sid).status, "done")
        b = self.cos.brain
        self.assertEqual(b.get_brain_item(old)["state"], "superseded")
        self.assertIn((new, "contradicts", old), {(l["from_id"], l["rel"], l["to_id"]) for l in b.memory.links_of(new)})
        self.assertTrue([r for r in b.reviews(["C08"]) if r["kind"] == "contradiction"])  # optional check row, nothing waits

    def test_second_run_makes_no_new_link(self):
        sid, ids = self.source("C09", "T5", "2026-08-01T10:00", ["Where will data be stored?", "It will be stored in India."],
                               [("question", "data-residency"), ("decision", "data-residency")])
        self.run_linker("C09", sid)
        count = len(self.cos.memory.links_of(ids[0]))
        self.run_linker("C09", sid)
        self.assertEqual(len(self.cos.memory.links_of(ids[0])), count)
        self.assertEqual(self.cos.brain.get_brain_item(ids[0])["state"], "resolved")

    def test_tools_refuse_items_of_another_area(self):
        _, (other,) = self.source("C10", "T6", "2026-08-02T10:00", ["We need a phased MVP."], [("requirement", "phased-mvp")])
        sid, (mine,) = self.source("C09", "T7", "2026-08-03T10:00", ["We need a lab portal."], [("requirement", "lab-integration")])
        ctx = SimpleNamespace(task=SimpleNamespace(area_id="C09"), run_id="R")
        from control_plane.company_brain import link_tools
        reply = json.loads(link_tools.make_add_links(self.cos.brain).fn({"links": [{"from": mine, "rel": "refines", "to": other}]}, ctx))
        self.assertIn("not in area", reply["error"])
        reply = json.loads(link_tools.make_set_state(self.cos.brain).fn({"item_id": other, "state": "dropped"}, ctx))
        self.assertIn("not in area", reply["error"])

    def test_judge_needs_every_link_and_no_wrong_link(self):
        good = {"found_links": 8, "expected_links": 8, "wrong_links": 0, "duplicates_merged": 2, "duplicates": 2, "failed_runs": []}
        self.assertTrue(judge(good)[2])
        self.assertFalse(judge({**good, "wrong_links": 1})[2])
        self.assertFalse(judge({**good, "found_links": 7})[2])


if __name__ == "__main__":
    unittest.main()
