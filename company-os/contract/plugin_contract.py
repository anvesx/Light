"""The plugin contract: the only thing agent packs and guardrails import from the core.

Six functions. Two are on the host (the runtime): run_task, add_tool.
Four are hooks a plugin may implement: before_request, before_tool, after_tool, after_reply.
If the core under this contract changes (our runtime, or dsh later), plugins do not change.
"""
from .types import ALLOW, Decision, ModelReply, ModelRequest, RunContext, RunResult, Task, ToolCall, ToolSpec


class Plugin:
    """Base class for plugins. Each hook passes things through unchanged unless a plugin overrides it."""

    name = "plugin"

    def before_request(self, req: ModelRequest, ctx: RunContext) -> ModelRequest:
        return req

    def before_tool(self, call: ToolCall, ctx: RunContext) -> Decision:
        return ALLOW

    def after_tool(self, call: ToolCall, result: str, ctx: RunContext) -> str:
        return result

    def after_reply(self, reply: ModelReply, ctx: RunContext) -> None:
        return None


class RunLog:
    """The run log the core writes to. The control plane supplies it; wiring passes it in."""

    def start_run(self, agent, trigger_kind, caller_id, area_id, started_at=None) -> str:
        raise NotImplementedError

    def log_step(self, run_id, step, detail=None, at=None) -> None:
        raise NotImplementedError

    def end_run(self, run_id, status, cost_usd=0.0, tokens_in=0, tokens_out=0, ended_at=None) -> None:
        raise NotImplementedError

    def scoped(self, area_ids):
        raise NotImplementedError


class WayInGate:
    """The check before a run starts. The control plane supplies it; wiring passes it in."""

    def admit(self, task: Task) -> Decision:
        raise NotImplementedError


class Host:
    """What any core must offer. Our runtime implements it; a dsh adapter would too."""

    def add_tool(self, spec: ToolSpec) -> None:
        raise NotImplementedError

    def run_task(self, task: Task) -> RunResult:
        raise NotImplementedError

    # Kit API (not plugin hooks): lets the lifecycle kit run one run in steps, with the same checks.
    def open_run(self, task: Task) -> RunContext | RunResult:
        """Runs the way-in check, starts the run, returns its context (or a refused RunResult)."""
        raise NotImplementedError

    def run_loop(self, ctx: RunContext, prompt: str, system: str = "") -> RunResult:
        raise NotImplementedError

    def invoke_tool(self, ctx: RunContext, name: str, args: dict) -> dict:
        """Calls one tool through the same before_tool/after_tool checks the model's calls get."""
        raise NotImplementedError

    def close_run(self, ctx: RunContext, status: str, final_text: str = "") -> RunResult:
        raise NotImplementedError
