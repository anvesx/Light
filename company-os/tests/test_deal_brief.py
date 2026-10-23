"""Deal brief agent: similar clients, ideas, kickoff questions, cite checks, role limits, exam."""
import json
import unittest

from agents.meeting_prep.deal_brief import replay_exam
from control_plane.company_brain.sample_content import seed_sample
from wiring.build_company_os import build_company_os


class DealBriefTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cos = build_company_os(agents=("deal_brief",))
        cls.ids = seed_sample(cls.cos.brain, cls.cos.data_conn)
        brain = cls.cos.brain
        sid = brain.add_source("C07", "chat", "Late note", "Reminders in Hindi maybe.", origin_ref="T-LOW", occurred_at="2026-10-02T10:00",
                               participants=[], language="en", lines=[{"line_no": 1, "speaker": "X", "text": "Reminders in Hindi maybe."}])
        cls.low = brain.add_brain_item("C07", "risk", "Reminders may need Hindi.", topic="reminders", source_id=sid, line_from=1,
                                       line_to=1, quote_raw="Reminders in Hindi maybe.", quote_clean="Reminders in Hindi maybe.",
                                       confidence=0.4)
        cls.result = cls.cos.run("deal_brief", "P03", "C07", inputs={"deal_id": "L20"})
        cls.brief = json.loads(cls.result.final_text)

    def test_run_is_done_and_brief_has_all_parts(self):
        self.assertEqual(self.result.status, "done")
        for key in ("similar", "closing_ideas", "risks", "kickoff_questions", "summary"):
            self.assertTrue(self.brief[key], key)
        self.assertEqual(self.brief["deal_id"], "L20")

    def test_similar_comes_from_the_library_only(self):
        self.assertEqual({s["client_label"] for s in self.brief["similar"]},
                         {"A healthcare clinic network", "A diagnostics lab"})

    def test_every_cite_is_a_playbook_or_this_deals_item(self):
        brain, library = self.cos.brain, {p["playbook_id"] for p in self.cos.brain.playbooks()}
        rows = self.brief["closing_ideas"] + self.brief["risks"] + self.brief["kickoff_questions"]
        for row in rows:
            self.assertTrue(row["cites"])
            for cite in row["cites"]:
                if cite.startswith("PB-"):
                    self.assertIn(cite, library)
                else:
                    self.assertEqual(brain.get_brain_item(cite)["area_id"], "C07")

    def test_unconfirmed_item_is_labelled(self):
        risk = next(r for r in self.brief["risks"] if self.low in r["cites"])
        self.assertTrue(risk["text"].startswith("Unconfirmed"))

    def test_kickoff_asks_what_past_clients_changed_late(self):
        topics = {q["topic"] for q in self.brief["kickoff_questions"]}
        self.assertTrue({"data-residency", "reminders"} <= topics)

    def test_brief_is_sent_privately_to_the_caller(self):
        self.assertTrue(any(m["kind"] == "deal_brief" for m in self.cos.outbox.messages("P03")))

    def test_similar_tool_output_has_no_client_area_or_item_ids(self):
        pack = self.cos.packs["deal_brief"]
        spec = next(t for t in pack.tools() if t.name == "similar_playbooks")
        text = spec.fn({"deal_id": "L20"}, _ctx(self.cos, "C07"))
        self.assertNotIn("area_id", text)
        self.assertNotIn('"I0', text)

    def _check(self, decision):
        pack, understood = self.cos.packs["deal_brief"], _understood(self.cos)
        return pack.check(_ctx(self.cos, "C07"), {"closing_ideas": decision.get("closing_ideas", []), "risks": decision.get("risks", []),
                                                  "kickoff_questions": decision.get("kickoff_questions", [])}, understood)

    def test_check_blocks_bad_cites_and_leaks(self):
        other = self.ids["items"]["SAMPLE-1:1"]  # an item of client C04
        for bad in (other, "PB-999999", "garbage"):
            problems = self._check({"closing_ideas": [{"text": "x", "topic": "pricing", "cites": [bad]}]})
            self.assertTrue(any(bad in p for p in problems), bad)
        name = self.cos.data_conn.execute("SELECT name FROM people WHERE is_devx = 0").fetchone()["name"]
        named = self._check({"risks": [{"text": f"Call {name} tomorrow", "cites": ["PB-000001"]}]})
        self.assertTrue(any("contact detail" in p for p in named))
        mail = self._check({"risks": [{"text": "Write to someone@example.com", "cites": ["PB-000001"]}]})
        self.assertTrue(any("contact detail" in p for p in mail))

    def test_check_blocks_unlabelled_unconfirmed(self):
        problems = self._check({"risks": [{"text": "Hindi reminders", "cites": [self.low]}]})
        self.assertTrue(any("Unconfirmed" in p for p in problems))

    def test_roles_and_areas(self):
        self.assertNotEqual(self.cos.run("deal_brief", "P05", "C07", inputs={"deal_id": "L20"}).status, "done")
        self.assertNotEqual(self.cos.run("deal_brief", "P03", "C04", inputs={"deal_id": "L05"}).status, "done")

    def test_growth_reads_deal_items_unfiltered(self):
        sb = self.cos.brain.scoped(["C07"])
        self.assertEqual([i["item_id"] for i in sb.brain_items("C07", deal_id="L20")],
                         [i["item_id"] for i in self.cos.brain.brain_items(["C07"], deal_id="L20")])

    def test_exam_passes(self):
        cos = build_company_os(agents=("deal_brief",))
        raw = replay_exam.run_exam(cos)
        self.assertTrue(replay_exam.judge(raw)[2], raw)


def _ctx(cos, area):
    """A run context for tool calls: the deal's area plus the library."""
    from contract.types import RunContext, Task
    task = Task(agent="deal_brief", caller_id="P03", area_id=area, trigger_kind="request", inputs={"deal_id": "L20"})
    return RunContext(run_id="R-test", task=task, memory=cos.memory.scoped([area, "playbooks"]))


def _understood(cos):
    ctx, pack = _ctx(cos, "C07"), cos.packs["deal_brief"]
    ctx.notes["invoke_tool"] = lambda name, args: {"result": next(t for t in pack.tools() if t.name == name).fn(args, ctx)}
    return pack.understand(ctx, pack.record(ctx))


if __name__ == "__main__":
    unittest.main()
