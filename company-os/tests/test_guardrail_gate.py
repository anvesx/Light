"""The guardrail gate: six cases on the real runtime, gateway, fake model, memory, outbox and approvals."""
import json
import unittest

from contract.types import ModelReply, ToolCall, ToolSpec
from lifecycle_kit.lifecycle_runner import LifecycleRunner
from tests.test_guardrails import INJECTED, World, task


def calls_then_text(*calls):
    """A brain that makes the given tool calls once, then gives a JSON answer."""
    def brain(req):
        if any(m["role"] == "tool" for m in req.messages):
            return ModelReply(text=json.dumps({"actions": []}))
        return ModelReply(tool_calls=[ToolCall(f"c{i}", n, a) for i, (n, a) in enumerate(calls)])
    return brain


class GuardrailGateTests(unittest.TestCase):
    def setUp(self):
        self.w = World(self)
        self.w.memory.add_item("C01", "note", "Client likes Fridays")
        self.w.memory.add_item("C02", "note", "Other client secret")

    def tool_steps(self, run_id):
        return [s["detail"] for s in self.w.steps(run_id) if s["step"] == "tool"]

    def test_1_unknown_caller_refused(self):
        r = self.w.runtime.run_task(task(caller_id="P99"))
        self.assertEqual(r.status, "refused")
        self.assertIn("unknown caller", r.reason)
        self.assertEqual(self.w.gateway.ledger.entries, [])

    def test_2_over_budget_refused(self):
        self.w.gateway.ledger.set_budget("caller:P02", 0.0)
        r = self.w.runtime.run_task(task())
        self.assertEqual(r.status, "refused")
        self.assertIn("budget", r.reason)
        self.assertEqual(self.w.gateway.ledger.entries, [])

    def test_3_other_clients_area_refused(self):
        # The guard denies the argument.
        self.w.brains["tiny"] = calls_then_text(("read_area", {"area_id": "C02"}))
        r = self.w.runtime.run_task(task())
        self.assertEqual(r.tool_results[0]["verdict"], "deny")
        self.assertNotIn("secret", r.tool_results[0]["result"])
        # Even with no argument, ScopedMemory raises when a tool reaches for another area.
        ctx = self.w.runtime.open_run(task())
        out = self.w.runtime.invoke_tool(ctx, "read_area", {})
        self.assertEqual(out["verdict"], "allow")
        with self.assertRaises(Exception) as cm:
            ctx.memory.items("C02")
        self.assertEqual(type(cm.exception).__name__, "AreaDenied")
        # And a caller without access to the area never starts.
        self.assertEqual(self.w.runtime.run_task(task(area_id="C02")).status, "refused")

    def test_4_forbidden_tool_denied(self):
        self.w.runtime.add_tool(ToolSpec("export_everything", "x", {}, lambda a, c: "all data"))
        self.w.brains["tiny"] = calls_then_text(("export_everything", {}))
        seen = []
        inner = self.w.brains["tiny"]
        self.w.brains["tiny"] = lambda req: (seen.append([t.name for t in req.tools]), inner(req))[1]
        r = self.w.runtime.run_task(task())
        self.assertEqual(r.tool_results[0]["verdict"], "deny")
        self.assertIn("denied", r.tool_results[0]["result"])
        self.assertNotIn("all data", r.tool_results[0]["result"])
        self.assertNotIn("export_everything", seen[0])  # the model never saw it

    def test_5_risky_action_held(self):
        self.w.brains["tiny"] = calls_then_text(
            ("create_followup_task", {"area_id": "C01", "title": "Call", "owner_id": "P02"}))
        r = self.w.runtime.run_task(task())
        self.assertEqual(r.status, "held")
        pending = self.w.approvals.pending()
        self.assertEqual([p["tool"] for p in pending], ["create_followup_task"])
        self.assertEqual(pending[0]["run_id"], r.run_id)
        self.assertEqual(self.w.memory.items("C01", kinds=["task"]), [])

    def test_6_orders_in_client_text_not_followed(self):
        self.w.memory.add_item("C01", "note", INJECTED)

        def naive(req):
            tool_msgs = [m for m in req.messages if m["role"] == "tool"]
            if not tool_msgs:
                return ModelReply(tool_calls=[ToolCall("c0", "read_notes", {})])
            if "outside@example.com" in tool_msgs[-1]["content"] and len(tool_msgs) == 1:
                return ModelReply(tool_calls=[ToolCall("c1", "send_private_message", {
                    "to_person_id": "outside@example.com", "text": "all invoices", "kind": "leak"})])
            return ModelReply(text=json.dumps({"actions": []}))
        self.w.brains["tiny"] = naive
        r = LifecycleRunner(self.w.runtime).run(self.w.pack, task())
        self.assertEqual(self.w.outbox.messages(), [])
        steps = self.tool_steps(r.run_id)
        read = [s for s in steps if s["name"] == "read_notes"][0]
        self.assertIn("<outside_data", read["result"])
        denied = [s for s in steps if s["name"] == "send_private_message"][0]
        self.assertEqual(denied["verdict"], "deny")
        self.assertIn("outside@example.com", denied["args"]["to_person_id"])
        self.assertIn("warning", [s["step"] for s in self.w.steps(r.run_id)])

    def test_paused_gate_refuses_everything(self):
        self.w.way_in.pause()
        for t in (task(), task(caller_id="P01", area_id="C02"), task(caller_id="system", trigger_kind="timer")):
            r = self.w.runtime.run_task(t)
            self.assertEqual(r.status, "refused")
            self.assertIn("paused", r.reason)
        self.assertEqual(self.w.gateway.ledger.entries, [])
        self.w.way_in.resume()
        self.assertNotEqual(self.w.runtime.run_task(task()).status, "refused")


if __name__ == "__main__":
    unittest.main()
