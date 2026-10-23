"""Real model through the `claude -p` CLI (uses the person's Claude plan). Tool calls use a JSON text protocol."""
import json
import os
import re
import shutil
import subprocess

from contract.types import ModelReply, ModelRequest, ToolCall, Usage

from .model_gateway import TransientModelError

PROTOCOL = (
    "Reply with ONE JSON object and nothing else (no prose, no code fence).\n"
    'To use tools: {"tool_calls": [{"name": "<tool name>", "args": {...}}]}\n'
    'To finish: {"final": "<your final answer as text; if the instructions ask for JSON, put that JSON text here>"}'
)


class ReplyFormatError(ValueError):
    """The model answered, but not in the JSON shape we asked for."""


def build_prompt(req: ModelRequest) -> str:
    tools = [{"name": t.name, "description": t.description, "input_schema": t.params} for t in req.tools]
    parts = [
        "SYSTEM INSTRUCTIONS:\n" + (req.system or "(none)"),
        "TOOLS (JSON schema list):\n" + json.dumps(tools),
        "REPLY FORMAT:\n" + PROTOCOL,
        "CONVERSATION (one JSON message per line, oldest first):",
    ]
    parts += [json.dumps(m) for m in req.messages]
    return "\n".join(parts)


def _strip_fences(text: str) -> str:
    body = text.strip()
    m = re.match(r"^```[a-zA-Z]*\s*\n?(.*?)\n?```$", body, re.S)
    return m.group(1).strip() if m else body


def parse_reply(text: str, ids_from: int = 0) -> ModelReply:
    """Read the model's JSON answer. Raises ReplyFormatError if it is not a tool_calls or final object."""
    try:
        data = json.loads(_strip_fences(text))
    except ValueError as e:
        raise ReplyFormatError(f"not valid JSON ({e})") from e
    if not isinstance(data, dict):
        raise ReplyFormatError("the JSON must be an object")
    if data.get("tool_calls"):
        calls = []
        for i, c in enumerate(data["tool_calls"]):
            if not isinstance(c, dict) or not isinstance(c.get("name"), str):
                raise ReplyFormatError("each tool call needs a string 'name'")
            calls.append(ToolCall(id=f"cli-{ids_from + i}", name=c["name"], args=c.get("args") or {}))
        return ModelReply(tool_calls=calls)
    if "final" not in data:
        raise ReplyFormatError("the JSON needs a 'tool_calls' list or a 'final' text")
    final = data["final"]
    return ModelReply(text=final if isinstance(final, str) else json.dumps(final))


def find_claude_binary(name="claude"):
    """The claude CLI path; Python's PATH can miss ~/.local/bin, where the installer puts it."""
    found = shutil.which(name)
    if found:
        return found
    local = os.path.expanduser(os.path.join("~", ".local", "bin", name))
    return local if os.path.exists(local) else name


class ClaudeCliModel:
    def __init__(self, binary: str = "claude", model_name: str = "sonnet", timeout: float = 180, runner=subprocess.run):
        self.binary = find_claude_binary(binary)
        self.model_name = model_name
        self.timeout = timeout
        self.runner = runner
        self._count = 0
        self.estimated_calls = 0   # calls where the CLI gave no usage and we guessed chars/4

    def complete(self, req: ModelRequest, agent: str) -> ModelReply:
        prompt = build_prompt(req)
        usage = Usage()
        error = ""
        for attempt in range(2):
            text = prompt if not error else (
                prompt + f"\n\nYour previous reply could not be read: {error}. Reply again with ONLY the JSON object.")
            result_text, call_usage = self._call_cli(text)
            usage = Usage(usage.input_tokens + call_usage.input_tokens, usage.output_tokens + call_usage.output_tokens)
            try:
                reply = parse_reply(result_text, self._count)
            except ReplyFormatError as e:
                error = str(e)
                continue
            self._count += len(reply.tool_calls)
            reply.usage = usage
            return reply
        raise TransientModelError(f"model reply could not be read twice: {error}")

    def _call_cli(self, prompt: str):
        cmd = [self.binary, "-p", "--output-format", "json", "--model", self.model_name]
        try:
            proc = self.runner(cmd, input=prompt, capture_output=True, text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired as e:
            raise TransientModelError(f"claude CLI timed out after {self.timeout}s") from e
        except OSError as e:
            raise TransientModelError(f"claude CLI could not start: {e}") from e
        if proc.returncode != 0:
            raise TransientModelError(f"claude CLI exited with {proc.returncode}: {(proc.stderr or '')[:200]}")
        try:
            envelope = json.loads(proc.stdout)
        except ValueError as e:
            raise TransientModelError(f"claude CLI output is not JSON: {e}") from e
        if not isinstance(envelope, dict) or envelope.get("is_error"):
            raise TransientModelError(f"claude CLI reported an error: {str(envelope)[:200]}")
        text = envelope.get("result") or ""
        return text, self._usage(envelope.get("usage"), prompt, text)

    def _usage(self, raw, prompt: str, text: str) -> Usage:
        if isinstance(raw, dict) and ("input_tokens" in raw or "output_tokens" in raw):
            cached = raw.get("cache_read_input_tokens", 0) + raw.get("cache_creation_input_tokens", 0)
            return Usage(input_tokens=raw.get("input_tokens", 0) + cached, output_tokens=raw.get("output_tokens", 0))
        self.estimated_calls += 1
        return Usage(input_tokens=len(prompt) // 4, output_tokens=len(text) // 4)
