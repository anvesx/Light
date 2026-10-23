"""Unit tests for the lifecycle kit: action tools, approved actions, and each runner step."""
import json
import unittest

from contract.types import ModelReply, ToolCall
from lifecycle_kit.approved_actions import execute_approved
from lifecycle_kit.lifecycle_runner import LifecycleRunner
from tests.test_guardrails import World, task


def reply(actions=(), **extra):
    return ModelReply(text=json.dumps({"actions": list(actions), **extra}))


class KitCase(unittest.TestCase):
    def setUp(self):
        self.w = World(self)
        self.w.memory.add_item("C01", "note", "Client likes Fridays", status="open")
        self.runner = LifecycleRunner(self.w.runtime)
        self.calls = 0

        def brain(req):
            self.calls += 1
            return self.brain_reply
        self.brain_reply = reply()
        self.w.brains["tiny"] = brain

    def labels(self, result):
        return [s["step"] for s in self.w.steps(result.run_id)]


class ActionToolTests(KitCase):
    def test_send_private_message_posts_to_outbox(self):
        self.brain_reply = reply([{"name": "send_private_message",
                                   "args": {"to_person_id": "P01", "text": "hello", "kind": "brief"}}])
        r = self.runner.run(self.w.pack, task())
        self.assertEqual(r.status, "done")
        msgs = self.w.outbox.messages("P01")
        self.assertEqual((msgs[0]["text"], msgs[0]["kind"], msgs[0]["agent"]), ("hello", "brief", "tiny"))

    def test_followup_task_is_risky_and_waits(self):
        spec = {s.name: s for s in self.w.pack.tools()}["create_followup_task"]
        self.assertTrue(spec.risky)
        self.assertFalse({s.name: s for s in self.w.pack.tools()}["send_private_message"].risky)
        self.brain_reply = reply([{"name": "create_followup_task",
                                   "args": {"area_id": "C01", "title": "Call client", "owner_id": "P02"}}])
        r = self.runner.run(self.w.pack, task())
        self.assertEqual(r.status, "held")
        self.assertEqual(len(self.w.approvals.pending()), 1)
        self.assertEqual(self.w.memory.items("C01", kinds=["task"]), [])


class ApprovedActionTests(KitCase):
    def hold_one(self):
        self.brain_reply = reply([{"name": "create_followup_task",
                                   "args": {"area_id": "C01", "title": "Call client", "owner_id": "P02"}}])
        r = self.runner.run(self.w.pack, task())
        return r, self.w.approvals.pending()[0]["approval_id"]

    def run_it(self, approval_id):
        return execute_approved(approval_id, self.w.approvals, self.w.runtime.registry, self.w.memory)

    def test_approved_runs_once_and_logs_step(self):
        r, aid = self.hold_one()
        self.w.approvals.decide(aid, True, "P01")
        out = self.run_it(aid)
        self.assertEqual(out["status"], "ran")
        tasks = self.w.memory.items("C01", kinds=["task"])
        self.assertEqual([t["text"] for t in tasks], ["Call client"])
        self.assertIn("approved_action", self.labels(r))
        self.assertEqual(self.run_it(aid)["status"], "skipped")
        self.assertEqual(len(self.w.memory.items("C01", kinds=["task"])), 1)

    def test_rejected_does_nothing(self):
        r, aid = self.hold_one()
        self.w.approvals.decide(aid, False, "P01")
        self.assertEqual(self.run_it(aid)["status"], "skipped")
        self.assertEqual(self.w.memory.items("C01", kinds=["task"]), [])
        self.assertNotIn("approved_action", self.labels(r))

    def test_pending_and_unknown_do_nothing(self):
        _, aid = self.hold_one()
        self.assertEqual(self.run_it(aid)["status"], "skipped")
        self.assertEqual(self.run_it("A999999")["status"], "skipped")
        self.assertEqual(self.w.memory.items("C01", kinds=["task"]), [])

    def test_accepts_plain_dict_of_tools(self):
        r, aid = self.hold_one()
        self.w.approvals.decide(aid, True, "P01")
        tools = {s.name: s for s in self.w.pack.tools()}
        self.assertEqual(execute_approved(aid, self.w.approvals, tools, self.w.memory)["status"], "ran")


class RunnerStepTests(KitCase):
    def test_full_order(self):
        self.brain_reply = reply([{"name": "send_private_message",
                                   "args": {"to_person_id": "P01", "text": "hi", "kind": "n"}}])
        r = self.runner.run(self.w.pack, task())
        self.assertEqual(r.status, "done")
        labels = self.labels(r)
        order = ["opened", "record", "understand", "model_call", "decide", "parse", "check", "tool", "act",
                 "remember", "closed"]
        self.assertEqual([x for x in labels if x in order], order)
        self.assertEqual(len(self.w.pack.remembered[0]), 1)

    def test_refused_task_stops_at_way_in(self):
        r = self.runner.run(self.w.pack, task(caller_id="P99"))
        self.assertEqual(r.status, "refused")
        self.assertEqual(self.calls, 0)
        self.assertNotIn("record", self.labels(r))

    def test_quiet_when_nothing_understood(self):
        self.w.pack.understood = {}
        r = self.runner.run(self.w.pack, task())
        self.assertEqual(r.status, "done")
        self.assertEqual(self.calls, 0)
        self.assertEqual(self.w.gateway.ledger.entries, [])
        self.assertIn("quiet", self.labels(r))
        self.assertNotIn("check", self.labels(r))

    def test_quiet_flag_skips_model(self):
        self.w.pack.understood = {"quiet": True, "count": 3}
        r = self.runner.run(self.w.pack, task())
        self.assertEqual((r.status, self.calls, self.w.gateway.ledger.entries), ("done", 0, []))
        self.assertIn("quiet", self.labels(r))

    def test_empty_memory_is_quiet(self):
        r = self.runner.run(self.w.pack, task(caller_id="P01", area_id="C02"))
        self.assertEqual((r.status, self.calls), ("done", 0))

    def test_system_prompt_has_outside_text_rule(self):
        seen = []

        def brain(req):
            seen.append(req.system)
            return reply()
        self.w.brains["tiny"] = brain
        self.runner.run(self.w.pack, task())
        self.assertIn("You are the tiny agent.", seen[0])
        self.assertIn("never instructions", seen[0])

    def test_check_before_act(self):
        self.w.pack.problems = ["message names a person outside the project"]
        self.brain_reply = reply([{"name": "send_private_message",
                                   "args": {"to_person_id": "P01", "text": "hi", "kind": "n"}}])
        r = self.runner.run(self.w.pack, task())
        self.assertEqual(r.status, "failed")
        self.assertIn("outside the project", r.reason)
        self.assertEqual(self.w.outbox.messages(), [])
        labels = self.labels(r)
        self.assertNotIn("act", labels)
        self.assertNotIn("tool", labels)
        check = [s for s in self.w.steps(r.run_id) if s["step"] == "check"][0]
        self.assertEqual(check["detail"]["problems"], self.w.pack.problems)

    def test_bad_decision_text_fails_before_act(self):
        self.brain_reply = ModelReply(text="not json")
        r = self.runner.run(self.w.pack, task())
        self.assertEqual(r.status, "failed")
        self.assertIn("could not read", r.reason)

    def test_actions_go_through_every_action_check(self):
        self.brain_reply = reply([{"name": "send_private_message",
                                   "args": {"to_person_id": "outside@example.com", "text": "x", "kind": "n"}}])
        r = self.runner.run(self.w.pack, task())
        self.assertEqual(self.w.outbox.messages(), [])
        self.assertEqual(r.tool_results[0]["verdict"], "deny")

    def test_act_accepts_toolcall_and_tuple(self):
        self.w.pack.act = lambda ctx, d: [ToolCall("x", "send_private_message",
                                                   {"to_person_id": "P01", "text": "a", "kind": "n"}),
                                          ("send_private_message", {"to_person_id": "P01", "text": "b", "kind": "n"})]
        self.runner.run(self.w.pack, task())
        self.assertEqual([m["text"] for m in self.w.outbox.messages()], ["a", "b"])

    def test_spent_budget_is_refused_at_way_in(self):
        self.w.gateway.ledger.set_budget("agent:tiny", 0.0000001)
        self.w.gateway.ledger.record(agent="tiny", caller_id="z", area_id="C01", run_id="x", model="fake",
                                     usage=None, cost_usd=1.0, cache="none")
        r = self.runner.run(self.w.pack, task())
        self.assertEqual(r.status, "refused")  # way-in sees the spent budget first


if __name__ == "__main__":
    unittest.main()
