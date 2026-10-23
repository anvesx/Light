"""Conformance checks for any Host (our runtime, or a dsh adapter later).

make_host(plugins, gate, replies) must return a Host whose model gives `replies` (ModelReply list) in order.
`gate` has admit(task) -> Decision; None means allow all.
"""
from .plugin_contract import Host, Plugin
from .types import ALLOW, Decision, ModelReply, RunResult, Task, ToolCall, ToolSpec


class _Recorder(Plugin):
    name = "recorder"

    def __init__(self, verdict=ALLOW):
        self.calls = []
        self.verdict = verdict

    def before_request(self, req, ctx):
        self.calls.append("before_request")
        return req

    def before_tool(self, call, ctx):
        self.calls.append("before_tool")
        return self.verdict

    def after_tool(self, call, result, ctx):
        self.calls.append("after_tool")
        return result

    def after_reply(self, reply, ctx):
        self.calls.append("after_reply")


class _Gate:
    def __init__(self, decision):
        self.decision = decision

    def admit(self, task):
        return self.decision


def _task():
    return Task(agent="conformance", caller_id="P01", area_id="C01", trigger_kind="test", prompt="go")


def _replies():
    return [ModelReply(tool_calls=[ToolCall("t1", "probe", {"n": 1})]), ModelReply(text="finished")]


def _setup(make_host, output="ok", plugin=None, gate=None, replies=None):
    ran = []

    def probe(args, ctx):
        ran.append(args)
        return output

    host = make_host([plugin] if plugin else [], gate, replies if replies is not None else _replies())
    host.add_tool(ToolSpec("probe", "a probe tool", {"type": "object", "properties": {}}, fn=probe))
    return host, ran


def run_conformance(test_case, make_host) -> None:
    """Run every check. `test_case` is a unittest.TestCase (used for its assert methods)."""
    host, _ = _setup(make_host)
    test_case.assertIsInstance(host, Host)

    with test_case.subTest("all four hooks are called"):
        rec = _Recorder()
        host, ran = _setup(make_host, plugin=rec)
        res = host.run_task(_task())
        test_case.assertEqual(res.status, "done")
        test_case.assertEqual(res.final_text, "finished")
        test_case.assertEqual(len(ran), 1)
        for hook in ("before_request", "after_reply", "before_tool", "after_tool"):
            test_case.assertIn(hook, rec.calls)

    with test_case.subTest("deny skips the tool"):
        rec = _Recorder(Decision("deny", "not allowed"))
        host, ran = _setup(make_host, plugin=rec)
        res = host.run_task(_task())
        test_case.assertEqual(ran, [])
        test_case.assertTrue(res.tool_results[0]["result"].startswith("denied:"))
        test_case.assertEqual(res.status, "done")

    with test_case.subTest("ask holds the run"):
        rec = _Recorder(Decision("ask", "needs a person"))
        host, ran = _setup(make_host, plugin=rec)
        res = host.run_task(_task())
        test_case.assertEqual(ran, [])
        test_case.assertEqual(res.status, "held")

    with test_case.subTest("output is capped at 8,000 characters"):
        host, _ = _setup(make_host, output="x" * 20000)
        res = host.run_task(_task())
        test_case.assertLessEqual(len(res.tool_results[0]["result"]), 8000)

    with test_case.subTest("the way-in gate can refuse"):
        rec = _Recorder()
        host, ran = _setup(make_host, plugin=rec, gate=_Gate(Decision("deny", "no access")))
        res = host.run_task(_task())
        test_case.assertIsInstance(res, RunResult)
        test_case.assertEqual(res.status, "refused")
        test_case.assertEqual(ran, [])
        test_case.assertNotIn("before_request", rec.calls)
