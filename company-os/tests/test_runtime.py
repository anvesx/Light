import unittest

from contract.plugin_contract import Plugin
from contract.types import Decision, ModelReply, Task, ToolCall, ToolSpec
from core.fake_model import FakeModel
from core.model_gateway import Gateway, TransientModelError
from core.agent_loop import Runtime
from core.tool_output_cap import cap_output


class FakeMemory:
    def __init__(self):
        self.steps, self.runs, self.ended, self.scopes = [], [], [], []

    def start_run(self, agent, trigger_kind, caller_id, area_id, started_at):
        self.runs.append((agent, trigger_kind, caller_id, area_id, started_at))
        return f"run{len(self.runs)}"

    def log_step(self, run_id, step, detail):
        self.steps.append((run_id, step, detail))

    def end_run(self, run_id, status, cost_usd, tokens_in, tokens_out, ended_at):
        self.ended.append((run_id, status, cost_usd, tokens_in, tokens_out, ended_at))

    def scoped(self, area_ids):
        self.scopes.append(list(area_ids))
        return {"areas": list(area_ids)}

    def labels(self):
        return [s[1] for s in self.steps]


class Gate:
    def __init__(self, verdict="allow", reason=""):
        self.d = Decision(verdict, reason)

    def admit(self, task):
        return self.d


class Spy(Plugin):
    def __init__(self, verdict="allow", reason=""):
        self.calls, self.d, self.requests = [], Decision(verdict, reason), []

    def before_request(self, req, ctx):
        self.calls.append("before_request")
        self.requests.append(req)
        return req

    def before_tool(self, call, ctx):
        self.calls.append("before_tool")
        return self.d

    def after_tool(self, call, result, ctx):
        self.calls.append("after_tool")
        return result + "!"

    def after_reply(self, reply, ctx):
        self.calls.append("after_reply")


def spec(name, fn=None, **kw):
    return ToolSpec(name, name, {"type": "object", "properties": {}}, fn=fn or (lambda a, c: "ok"), **kw)


def task(**kw):
    return Task(agent="ag", caller_id="P01", area_id="C01", trigger_kind="test", prompt="go", **kw)


def build(replies, plugins=(), gate=None, **kw):
    """replies: list of ModelReply or Exception, used in order (the last repeats)."""
    seq, calls = list(replies), []

    def brain(req):
        calls.append(req)
        item = seq.pop(0) if len(seq) > 1 else seq[0]
        if isinstance(item, Exception):
            raise item
        return item

    mem = FakeMemory()
    gw = Gateway({"fake": FakeModel({"ag": brain})})
    return Runtime(gw, mem, gate or Gate(), plugins, **kw), mem, calls


def tc(name, id="t1", **args):
    return ModelReply(tool_calls=[ToolCall(id, name, args)])


class RuntimeTests(unittest.TestCase):
    def test_simple_final_answer_and_log(self):
        rt, mem, calls = build([ModelReply(text="hello")])
        res = rt.run_task(task())
        self.assertEqual((res.status, res.final_text), ("done", "hello"))
        self.assertEqual(mem.labels(), ["opened", "model_call", "closed"])
        self.assertEqual(mem.ended[0][1], "done")
        self.assertGreater(mem.ended[0][2], 0)
        self.assertEqual(mem.scopes, [["C01"]])
        self.assertEqual(len(calls), 1)

    def test_tools_sent_sorted_by_name(self):
        rt, mem, calls = build([ModelReply(text="x")])
        for n in ("zeta", "alpha", "mid"):
            rt.add_tool(spec(n))
        rt.run_task(task())
        self.assertEqual([t.name for t in calls[0].tools], ["alpha", "mid", "zeta"])

    def test_four_hooks_called(self):
        spy = Spy()
        rt, mem, _ = build([tc("echo"), ModelReply(text="end")], plugins=[spy])
        rt.add_tool(spec("echo"))
        res = rt.run_task(task())
        for h in ("before_request", "before_tool", "after_tool", "after_reply"):
            self.assertIn(h, spy.calls)
        self.assertEqual(res.tool_results[0]["result"], "ok!")
        self.assertEqual(spy.calls.count("before_request"), 2)

    def test_deny_skips_tool(self):
        ran = []
        rt, mem, _ = build([tc("echo"), ModelReply(text="end")], plugins=[Spy("deny", "no way")])
        rt.add_tool(spec("echo", lambda a, c: ran.append(1) or "ok"))
        res = rt.run_task(task())
        self.assertEqual(ran, [])
        self.assertEqual(res.tool_results[0]["result"], "denied: no way")
        self.assertEqual(res.tool_results[0]["verdict"], "deny")
        self.assertEqual(res.status, "done")

    def test_first_non_allow_wins(self):
        a, b, c = Spy(), Spy("deny", "b says no"), Spy("ask", "c asks")
        rt, _, _ = build([tc("echo"), ModelReply(text="end")], plugins=[a, b, c])
        rt.add_tool(spec("echo"))
        res = rt.run_task(task())
        self.assertEqual(res.tool_results[0]["result"], "denied: b says no")
        self.assertNotIn("before_tool", c.calls)

    def test_ask_holds_run(self):
        ran = []
        rt, mem, calls = build([tc("echo"), ModelReply(text="end")], plugins=[Spy("ask", "needs boss")])
        rt.add_tool(spec("echo", lambda a, c: ran.append(1) or "ok"))
        res = rt.run_task(task())
        self.assertEqual(ran, [])
        self.assertEqual(res.status, "held")
        self.assertEqual(res.tool_results[0]["result"], "held for approval: needs boss")
        self.assertEqual(len(calls), 1)
        self.assertEqual(mem.ended[0][1], "held")

    def test_output_capped(self):
        rt, _, _ = build([tc("big"), ModelReply(text="end")])
        rt.add_tool(spec("big", lambda a, c: "y" * 30000))
        res = rt.run_task(task())
        out = res.tool_results[0]["result"]
        self.assertLessEqual(len(out), 8000)
        self.assertIn("cut", out)
        self.assertEqual(cap_output("short"), "short")

    def test_transient_retry(self):
        err = TransientModelError("busy")
        rt, mem, calls = build([err, err, ModelReply(text="ok")], retries=2)
        self.assertEqual(rt.run_task(task()).status, "done")
        self.assertEqual(len(calls), 3)
        self.assertEqual(mem.labels().count("retry"), 2)
        rt2, _, calls2 = build([err], retries=2)
        res = rt2.run_task(task())
        self.assertEqual(res.status, "failed")
        self.assertEqual(len(calls2), 3)

    def test_unknown_tool_and_exception(self):
        def boom(a, c):
            raise ValueError("bad thing")
        replies = [ModelReply(tool_calls=[ToolCall("1", "nope", {}), ToolCall("2", "boom", {})]), ModelReply(text="end")]
        rt, _, _ = build(replies)
        rt.add_tool(spec("boom", boom))
        res = rt.run_task(task())
        self.assertEqual(res.tool_results[0]["result"], "error: unknown tool")
        self.assertEqual(res.tool_results[1]["result"], "error: bad thing")
        self.assertEqual(res.status, "done")

    def test_max_steps(self):
        rt, mem, calls = build([tc("echo")], max_steps=3)
        rt.add_tool(spec("echo"))
        res = rt.run_task(task())
        self.assertEqual(res.status, "max_steps")
        self.assertEqual(len(calls), 3)

    def test_gate_refusal(self):
        spy = Spy()
        rt, mem, calls = build([ModelReply(text="x")], plugins=[spy], gate=Gate("deny", "unknown caller"))
        res = rt.run_task(task())
        self.assertEqual((res.status, res.reason), ("refused", "unknown caller"))
        self.assertEqual(calls, [])
        self.assertEqual(spy.calls, [])
        self.assertEqual(mem.labels(), ["refused"])
        self.assertEqual(mem.ended[0][1], "refused")

    def test_every_step_logged(self):
        rt, mem, _ = build([tc("echo"), tc("echo", "t2"), ModelReply(text="end")])
        rt.add_tool(spec("echo"))
        rt.run_task(task())
        self.assertEqual(mem.labels(), ["opened", "model_call", "tool", "model_call", "tool", "model_call", "closed"])
        tool_step = [s for s in mem.steps if s[1] == "tool"][0][2]
        self.assertEqual((tool_step["name"], tool_step["verdict"], tool_step["result"]), ("echo", "allow", "ok"))

    def test_messages_shape(self):
        rt, _, calls = build([tc("echo", "t1", q=1), ModelReply(text="end")])
        rt.add_tool(spec("echo"))
        rt.run_task(task())
        msgs = calls[1].messages
        self.assertEqual([m["role"] for m in msgs], ["user", "assistant", "tool"])
        self.assertEqual(msgs[1]["tool_calls"], [{"id": "t1", "name": "echo", "args": {"q": 1}}])
        self.assertEqual(msgs[2]["tool_call_id"], "t1")

    def test_small_window_compacts_before_a_model_call_and_logs_it(self):
        from core.compaction import INSTRUCTION
        turns = [0]

        def brain(req):
            if req.messages[0]["content"].startswith(INSTRUCTION[:30]):
                return ModelReply(text="## Goal\n- finish")
            turns[0] += 1
            return tc("big", f"t{turns[0]}") if turns[0] < 12 else ModelReply(text="end")

        mem = FakeMemory()
        rt = Runtime(Gateway({"fake": FakeModel({"ag": brain})}), mem, Gate(), max_steps=20, window_tokens=1500)
        rt.add_tool(spec("big", lambda a, c: "z" * 800))
        res = rt.run_task(task())
        self.assertEqual(res.status, "done")
        notes = [s[2] for s in mem.steps if s[1] == "compaction"]
        self.assertTrue(notes)
        self.assertLess(notes[0]["after_tokens"], notes[0]["before_tokens"])
        self.assertGreater(notes[0]["folded_messages"], 0)

    def test_kit_api_runs_same_hooks(self):
        spy = Spy("deny", "kit no")
        rt, mem, _ = build([ModelReply(text="done text")], plugins=[spy])
        rt.add_tool(spec("echo"))
        ctx = rt.open_run(task())
        out = rt.invoke_tool(ctx, "echo", {"a": 1})
        self.assertEqual((out["result"], out["verdict"]), ("denied: kit no", "deny"))
        self.assertIn("before_tool", spy.calls)
        spy.d = Decision("allow")
        out = rt.invoke_tool(ctx, "echo", {})
        self.assertEqual(out["result"], "ok!")
        self.assertIn("after_tool", spy.calls)
        res = rt.run_loop(ctx, "think", system="sys")
        self.assertEqual(res.status, "done")
        self.assertEqual(spy.requests[-1].system, "sys")
        closed = rt.close_run(ctx, "done", res.final_text)
        self.assertEqual(closed.final_text, "done text")
        self.assertEqual(len(closed.tool_results), 2)
        self.assertEqual(mem.ended[0][1], "done")

    def test_kit_invoke_ask_holds(self):
        rt, _, _ = build([ModelReply(text="x")], plugins=[Spy("ask", "risky")])
        rt.add_tool(spec("echo"))
        ctx = rt.open_run(task())
        out = rt.invoke_tool(ctx, "echo", {})
        self.assertEqual(out["verdict"], "ask")
        self.assertTrue(ctx.held)

    def test_open_run_refused_returns_result(self):
        rt, _, _ = build([ModelReply(text="x")], gate=Gate("deny", "nope"))
        self.assertEqual(rt.open_run(task()).status, "refused")


if __name__ == "__main__":
    unittest.main()
