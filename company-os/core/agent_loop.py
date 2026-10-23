"""Our thin agent runtime: the loop, the tool checks, and the run log. Implements the contract's Host.
The run log and way-in gate arrive as contract objects (RunLog, WayInGate)."""
import json

from contract.plugin_contract import Host, RunLog, WayInGate
from contract.types import ALLOW, ModelRequest, RunContext, RunResult, ToolCall
from core.fixed_clock import FixedClock
from core.model_gateway import BudgetExceeded, TransientModelError

from .compaction import compact_if_needed
from .tool_output_cap import cap_output
from .tool_registry import ToolRegistry


class Runtime(Host):
    def __init__(self, gateway, memory_store: RunLog, way_in_gate: WayInGate, plugins=(), max_steps=12, retries=2, clock=None,
                 window_tokens=200_000):
        self.gateway = gateway
        self.memory = memory_store
        self.gate = way_in_gate
        self.plugins = list(plugins)
        self.max_steps = max_steps
        self.retries = retries
        self.window_tokens = window_tokens
        self.clock = clock or getattr(gateway, "clock", None) or FixedClock()
        self.registry = ToolRegistry()

    def add_tool(self, spec) -> None:
        self.registry.add(spec)

    def run_task(self, task) -> RunResult:
        ctx = self.open_run(task)
        if isinstance(ctx, RunResult):
            return ctx
        outcome = self.run_loop(ctx, task.prompt)
        return self.close_run(ctx, outcome.status, outcome.final_text)

    def open_run(self, task):
        run_id = self.memory.start_run(task.agent, task.trigger_kind, task.caller_id, task.area_id, self.clock.now)
        decision = self.gate.admit(task)
        if decision.verdict != "allow":
            self.memory.log_step(run_id, "refused", {"verdict": decision.verdict, "reason": decision.reason})
            self.memory.end_run(run_id, "refused", 0.0, 0, 0, self.clock.now)
            return RunResult(run_id=run_id, status="refused", reason=decision.reason)
        self.memory.log_step(run_id, "opened", {"agent": task.agent, "area_id": task.area_id})
        extra = self.gate.extra_read_areas(task) if hasattr(self.gate, "extra_read_areas") else set()
        ctx = RunContext(run_id=run_id, task=task, memory=self.memory.scoped([task.area_id, *sorted(extra - {task.area_id})]))
        ctx.notes["runtime"] = {"cost": 0.0, "tokens_in": 0, "tokens_out": 0, "results": [],
                                "reason": "", "kit_calls": 0}
        return ctx

    def run_loop(self, ctx: RunContext, prompt: str, system: str = "") -> RunResult:
        state = ctx.notes["runtime"]
        messages = [{"role": "user", "content": prompt}]
        limit = min(self.max_steps, ctx.task.max_steps)
        final_text, status = "", "max_steps"
        for _ in range(limit):
            tools = self.registry.sorted_specs()
            messages = self._compact(ctx, messages, system, tools)
            req = ModelRequest(model=ctx.task.model, system=system, messages=list(messages), tools=tools)
            for p in self.plugins:
                req = p.before_request(req, ctx)
            try:
                reply = self._call_model(ctx, req)
            except (TransientModelError, BudgetExceeded) as e:
                state["reason"] = f"{type(e).__name__}: {e}"
                self.memory.log_step(ctx.run_id, "model_failed", {"reason": state["reason"]})
                status = "failed"
                break
            for p in self.plugins:
                p.after_reply(reply, ctx)
            state["cost"] += reply.cost_usd
            state["tokens_in"] += reply.usage.input_tokens + reply.usage.cache_read_tokens + reply.usage.cache_write_tokens
            state["tokens_out"] += reply.usage.output_tokens
            self.memory.log_step(ctx.run_id, "model_call", {
                "model": req.model, "tool_calls": [c.name for c in reply.tool_calls], "text": reply.text,
                "tokens_in": reply.usage.input_tokens, "tokens_out": reply.usage.output_tokens,
                "cost_usd": reply.cost_usd, "cache_hit": reply.cache_hit})
            messages.append({"role": "assistant", "content": reply.text,
                             "tool_calls": [{"id": c.id, "name": c.name, "args": c.args} for c in reply.tool_calls]})
            if not reply.tool_calls:
                final_text, status = reply.text, "done"
                break
            for call in reply.tool_calls:
                entry = self._run_tool_call(ctx, call)
                messages.append({"role": "tool", "tool_call_id": call.id, "name": call.name,
                                 "content": entry["result"]})
            if ctx.held:
                status = "held"
                break
        if status == "max_steps":
            state["reason"] = f"stopped after {limit} steps"
        return RunResult(run_id=ctx.run_id, status=status, final_text=final_text,
                         tool_results=list(state["results"]), cost_usd=state["cost"], reason=state["reason"])

    def invoke_tool(self, ctx: RunContext, name: str, args: dict) -> dict:
        state = ctx.notes["runtime"]
        state["kit_calls"] += 1
        return self._run_tool_call(ctx, ToolCall(id=f"kit-{state['kit_calls']}", name=name, args=args))

    def close_run(self, ctx: RunContext, status: str, final_text: str = "") -> RunResult:
        state = ctx.notes["runtime"]
        ctx.status = status
        self.memory.log_step(ctx.run_id, "closed", {"status": status, "final_text": final_text})
        self.memory.end_run(ctx.run_id, status, state["cost"], state["tokens_in"], state["tokens_out"],
                            self.clock.now)
        return RunResult(run_id=ctx.run_id, status=status, final_text=final_text,
                         tool_results=list(state["results"]), cost_usd=state["cost"], reason=state["reason"])

    def _compact(self, ctx, messages, system, tools):
        """Fold the old middle of the conversation into a summary when it nears the window; log the note."""
        prefix = (len(system) + sum(len(t.name) + len(t.description) + len(json.dumps(t.params)) for t in tools)) // 4
        try:
            messages, note = compact_if_needed(messages, window_tokens=self.window_tokens, prefix_tokens=prefix,
                                               model_call=lambda m: self._summarise(ctx, m))
        except (TransientModelError, BudgetExceeded):  # no summary: carry on with the full conversation
            return messages
        if note is not None:
            self.memory.log_step(ctx.run_id, "compaction", note.as_dict())
        return messages

    def _summarise(self, ctx, messages) -> str:
        reply = self.gateway.call(ModelRequest(model=ctx.task.model, system="", messages=messages, tools=[], cache_prefix=False),
                                  agent=ctx.task.agent, caller_id=ctx.task.caller_id, area_id=ctx.task.area_id,
                                  run_id=ctx.run_id)
        state = ctx.notes["runtime"]
        state["cost"] += reply.cost_usd
        state["tokens_in"] += reply.usage.input_tokens + reply.usage.cache_read_tokens + reply.usage.cache_write_tokens
        state["tokens_out"] += reply.usage.output_tokens
        return reply.text

    def _call_model(self, ctx, req):
        for attempt in range(self.retries + 1):
            try:
                return self.gateway.call(req, agent=ctx.task.agent, caller_id=ctx.task.caller_id,
                                         area_id=ctx.task.area_id, run_id=ctx.run_id)
            except TransientModelError as e:
                self.memory.log_step(ctx.run_id, "retry", {"attempt": attempt + 1, "error": str(e)})
                if attempt == self.retries:
                    raise

    def _run_tool_call(self, ctx, call: ToolCall) -> dict:
        verdict = ALLOW
        for p in self.plugins:
            d = p.before_tool(call, ctx)
            if d.verdict != "allow":
                verdict = d
                break
        if verdict.verdict == "deny":
            result = f"denied: {verdict.reason}"
        elif verdict.verdict == "ask":
            if not ctx.held:
                ctx.held.append(call.id)  # a plugin that made an approval has already added its id
            ctx.status = "held"
            result = f"held for approval: {verdict.reason}"
        else:
            result = self._execute(ctx, call)
        entry = {"call": call, "result": result, "verdict": verdict.verdict}
        ctx.notes["runtime"]["results"].append(entry)
        self.memory.log_step(ctx.run_id, "tool", {"name": call.name, "args": call.args,
                                                  "verdict": verdict.verdict, "reason": verdict.reason,
                                                  "result": result})
        return entry

    def _execute(self, ctx, call: ToolCall) -> str:
        spec = self.registry.get(call.name)
        if spec is None:
            result = "error: unknown tool"
        else:
            try:
                result = str(spec.fn(call.args, ctx))
            except Exception as e:  # a broken tool must not stop the run
                result = f"error: {e}"
        result = cap_output(result)
        for p in self.plugins:
            result = p.after_tool(call, result, ctx)
        return result
