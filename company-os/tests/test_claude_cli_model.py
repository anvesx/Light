"""Tests for the real-model path: the CLI model with a fake command runner, and a full pack run through it."""
import json
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace

from agents.finance.watch import fake_brain
from contract.types import ModelRequest, ToolSpec
from core.claude_cli_model import ClaudeCliModel, build_prompt
from core.model_gateway import TransientModelError
from wiring.build_company_os import build_company_os


def envelope(result, usage=None, code=0):
    body = {"type": "result", "result": result}
    if usage is not None:
        body["usage"] = usage
    return SimpleNamespace(returncode=code, stdout=json.dumps(body), stderr="boom")


class FakeRunner:
    """Returns the queued replies in order and remembers every command and prompt."""
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, cmd, input="", **kw):
        self.calls.append({"cmd": cmd, "input": input, "kw": kw})
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def request():
    tool = ToolSpec(name="lookup", description="Find a thing", params={"type": "object", "properties": {}})
    return ModelRequest(model="claude-cli", system="Be brief.", messages=[{"role": "user", "content": "hi"}],
                        tools=[tool])


class ClaudeCliModelTests(unittest.TestCase):
    def model(self, *replies):
        self.runner = FakeRunner(*replies)
        return ClaudeCliModel(runner=self.runner)

    def test_prompt_has_system_tools_format_and_conversation(self):
        prompt = build_prompt(request())
        for part in ("Be brief.", '"input_schema"', '"tool_calls"', '"final"', '"content": "hi"'):
            self.assertIn(part, prompt)

    def test_command_shape(self):
        m = self.model(envelope('{"final": "ok"}', {"input_tokens": 1, "output_tokens": 1}))
        m.complete(request(), "a")
        cmd = self.runner.calls[0]["cmd"]
        self.assertTrue(cmd[0].endswith("claude")); self.assertEqual(cmd[1], "-p")
        self.assertIn("--output-format", cmd)
        self.assertIn("--model", cmd)
        self.assertIn("timeout", self.runner.calls[0]["kw"])

    def test_tool_call_reply(self):
        m = self.model(envelope('{"tool_calls": [{"name": "lookup", "args": {"q": 1}}]}', {"input_tokens": 5}))
        reply = m.complete(request(), "a")
        self.assertEqual([(c.name, c.args) for c in reply.tool_calls], [("lookup", {"q": 1})])
        self.assertEqual(reply.text, "")

    def test_final_reply(self):
        reply = self.model(envelope('{"final": "{\\"findings\\": []}"}', {})).complete(request(), "a")
        self.assertEqual(reply.text, '{"findings": []}')
        self.assertFalse(reply.tool_calls)

    def test_fenced_reply(self):
        reply = self.model(envelope('```json\n{"final": "done"}\n```', {})).complete(request(), "a")
        self.assertEqual(reply.text, "done")

    def test_one_malformed_reply_then_valid(self):
        m = self.model(envelope("I think so", {"input_tokens": 10, "output_tokens": 2}),
                       envelope('{"final": "ok"}', {"input_tokens": 12, "output_tokens": 3}))
        reply = m.complete(request(), "a")
        self.assertEqual(reply.text, "ok")
        self.assertIn("could not be read", self.runner.calls[1]["input"])
        self.assertEqual((reply.usage.input_tokens, reply.usage.output_tokens), (22, 5))

    def test_two_malformed_replies_fail(self):
        with self.assertRaises(TransientModelError):
            self.model(envelope("nope"), envelope("still nope")).complete(request(), "a")

    def test_timeout_is_transient(self):
        m = self.model(subprocess.TimeoutExpired("claude", 1))
        with self.assertRaises(TransientModelError):
            m.complete(request(), "a")

    def test_nonzero_exit_is_transient(self):
        with self.assertRaises(TransientModelError):
            self.model(envelope("", code=1)).complete(request(), "a")

    def test_usage_mapping_includes_cache_tokens(self):
        usage = {"input_tokens": 10, "output_tokens": 4, "cache_read_input_tokens": 100,
                 "cache_creation_input_tokens": 20}
        m = self.model(envelope('{"final": "x"}', usage))
        reply = m.complete(request(), "a")
        self.assertEqual((reply.usage.input_tokens, reply.usage.output_tokens), (130, 4))
        self.assertEqual(m.estimated_calls, 0)

    def test_missing_usage_is_estimated(self):
        m = self.model(envelope('{"final": "abcdefgh"}'))
        reply = m.complete(request(), "a")
        self.assertGreater(reply.usage.input_tokens, 0)
        self.assertEqual(m.estimated_calls, 1)


def finance_runner(cmd, input="", **kw):
    """Acts like the real model for finance_watch: reads the findings from the prompt, answers with the fake brain's JSON."""
    lines = input.split("CONVERSATION (one JSON message per line, oldest first):\n", 1)[1].splitlines()
    first = json.loads(lines[0])
    reply = fake_brain.brain(ModelRequest(model="x", system="", messages=[first], tools=[]))
    return envelope(json.dumps({"final": reply.text}), {"input_tokens": 2000, "output_tokens": 300})


class SonnetOnlyTests(unittest.TestCase):
    def test_the_real_model_is_sonnet(self):
        from core.model_prices import price_name
        runner = FakeRunner(envelope(json.dumps({"final": "ok"})))
        model = ClaudeCliModel(runner=runner)
        model.complete(ModelRequest(model="claude-cli", system="s", messages=[{"role": "user", "content": "hi"}], tools=[]), "ag")
        cmd = runner.calls[0]["cmd"]
        self.assertEqual(cmd[cmd.index("--model") + 1], "sonnet")
        self.assertEqual(price_name("claude-cli"), "sonnet-5-5")

    def test_no_runtime_path_names_opus(self):
        import pathlib
        root = pathlib.Path(__file__).resolve().parent.parent
        named = []
        for folder in ("core", "control_plane", "wiring", "lifecycle_kit", "agents", "web_console", "evaluation"):
            for path in (root / folder).rglob("*.py"):
                if "opus" in path.read_text(encoding="utf-8").lower() and path.name != "model_prices.py":
                    named.append(str(path.relative_to(root)))
        self.assertEqual(named, [])


class RealModelEndToEndTests(unittest.TestCase):
    def test_finance_watch_runs_through_cli_backend(self):
        d = tempfile.mkdtemp(prefix="cli_e2e_")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        cos = build_company_os(agents=("finance_watch",), state_dir=d, real_model="claude-cli")
        self.addCleanup(cos.data_conn.close)
        cos.gateway._backends["claude-cli"].runner = finance_runner
        result = cos.run("finance_watch", "P07", "devx-internal", inputs={"as_of": "2026-09-25"}, model="claude-cli")
        self.assertEqual(result.status, "held")
        self.assertIn("INV051", cos.outbox.messages("P07")[0]["text"])
        self.assertGreater(result.cost_usd, 0)

    def test_default_has_no_real_backend(self):
        d = tempfile.mkdtemp(prefix="cli_e2e_")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        cos = build_company_os(agents=("finance_watch",), state_dir=d)
        self.addCleanup(cos.data_conn.close)
        self.assertNotIn("claude-cli", cos.gateway._backends)


if __name__ == "__main__":
    unittest.main()
