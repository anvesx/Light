"""Tests for the live session: guarded run, suggestions on LC01 and LC02, the timing limit and the end summary."""
import tempfile
import unittest

from agents.meeting_prep.live_copilot.call_brain_seed import seed_history
from agents.meeting_prep.live_copilot.live_session import LiveSession, Refused
from agents.meeting_prep.live_copilot.replay_exam import judge, run_exam
from wiring.build_company_os import build_company_os


def play(session):
    out = []
    for n in sorted(session.script):
        out += session.hear(n)["suggestions"]
    return out


class LiveSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cos = build_company_os(agents=("live_copilot",), state_dir=tempfile.mkdtemp(prefix="live_test_"))
        seed_history(cls.cos)

    def steps(self, run_id, name):
        return [s["detail"] for s in self.cos.memory.run_steps(run_id) if s["step"] == name]

    def test_lc02_finds_the_contradiction(self):
        s = LiveSession.start(self.cos, "P05", "LC02")
        got = play(s)
        self.assertEqual([(x["line_no"], x["kind"], x["topic"]) for x in got], [(4, "contradiction", "reminders")])
        self.assertEqual(got[0]["cites"][0]["origin_ref"], "SRC25")
        self.assertEqual(got[0]["cites"][0]["line_no"], 14)

    def test_lc01_suggestions_and_limits(self):
        got = play(LiveSession.start(self.cos, "P03", "LC01"))
        self.assertEqual([(x["line_no"], x["topic"]) for x in got], [(4, "insurance-claims"), (6, "pricing"), (8, "reminders"),
                                                                    (10, "data-residency"), (12, "language-support")])
        self.assertEqual(len({x["topic"] for x in got}), len(got))

    def test_every_read_is_a_logged_allowed_tool_call(self):
        s = LiveSession.start(self.cos, "P03", "LC01")
        tools = self.steps(s.run_id, "tool")
        self.assertEqual([t["name"] for t in tools], ["live_call_script", "live_call_brain", "live_call_brain", "live_call_brain"])
        self.assertTrue(all(t["verdict"] == "allow" for t in tools))

    def test_growth_reads_the_library_and_csm_does_not(self):
        growth = LiveSession.start(self.cos, "P03", "LC01")
        self.assertTrue(growth.listener.checklist)
        csm = LiveSession.start(self.cos, "P05", "LC02")
        self.assertEqual(csm.listener.checklist, {})
        self.assertNotIn("playbooks", csm.ctx.memory.area_ids)
        self.assertIn("playbooks", growth.ctx.memory.area_ids)

    def test_wrong_person_is_refused(self):
        with self.assertRaises(Refused):
            LiveSession.start(self.cos, "P05", "LC01")
        with self.assertRaises(Refused):
            LiveSession.start(self.cos, "P03", "LC99")

    def test_admin_may_join_any_call(self):
        self.assertEqual(LiveSession.start(self.cos, "P01", "LC02").call["area_id"], "C04")

    def test_one_run_one_model_call_and_source_saved(self):
        s = LiveSession.start(self.cos, "P05", "LC02")
        play(s)
        out = s.end()
        self.assertEqual(out["status"], "done")
        self.assertEqual(len(self.steps(out["run_id"], "model_call")), 1)
        self.assertEqual(len(self.steps(out["run_id"], "suggestion")), 1)
        src = self.cos.brain.get_source(out["source_id"])
        self.assertEqual(src["kind"], "live_call")
        self.assertEqual(len(self.cos.brain.source_lines(out["source_id"])), 8)
        self.assertEqual(s.end(), out)  # a second end changes nothing

    def test_no_model_call_while_hearing(self):
        s = LiveSession.start(self.cos, "P03", "LC01")
        play(s)
        self.assertEqual(self.steps(s.run_id, "model_call"), [])

    def test_typed_line_is_checked(self):
        s = LiveSession.start(self.cos, "P05", "LC02")
        r = s.hear(text="Please send reminders by SMS from now on.")
        self.assertEqual(r["suggestions"][0]["kind"], "contradiction")

    def test_hear_is_fast(self):
        times = []
        for who, call in (("P03", "LC01"), ("P05", "LC02")):
            s = LiveSession.start(self.cos, who, call)
            play(s)
            times += s.timings_ms
        times.sort()
        self.assertLess(times[int(0.95 * len(times))], 200)
        self.assertLess(max(times), 200)

    def test_exam_passes(self):
        result = run_exam(self.cos)
        self.assertTrue(judge(result)[2], result)


if __name__ == "__main__":
    unittest.main()
