"""Runs one task through the lifecycle: record, understand, decide, check, act, remember."""
from dataclasses import replace

from contract.types import RunResult, ToolCall
from control_plane.guardrails.outside_text import RULE


class LifecycleRunner:
    def __init__(self, runtime):
        self.runtime = runtime
        self.log = runtime.memory.log_step

    def run(self, pack, task) -> RunResult:
        rt = self.runtime
        ctx = rt.open_run(task)
        if isinstance(ctx, RunResult):
            return ctx
        # Packs read data through this, so every read passes the every-action check and lands in the audit log.
        ctx.notes["invoke_tool"] = lambda name, args: rt.invoke_tool(ctx, name, args)
        recorded = pack.record(ctx)
        self.log(ctx.run_id, "record", {"summary": _short(recorded)})
        understood = pack.understand(ctx, recorded)
        self.log(ctx.run_id, "understand", {"summary": _short(understood)})
        if not understood or understood.get("quiet"):
            self.log(ctx.run_id, "quiet", {"reason": "nothing to decide; no model call"})
            return rt.close_run(ctx, "done", "quiet")

        system = (pack.system_prompt() + "\n\n" + RULE).strip()
        outcome = rt.run_loop(ctx, pack.decision_prompt(understood), system=system)
        self.log(ctx.run_id, "decide", {"status": outcome.status})
        if outcome.status != "done":
            return replace(rt.close_run(ctx, outcome.status, outcome.final_text), reason=outcome.reason)
        try:
            decision = pack.parse_decision(outcome.final_text)
        except Exception as e:
            return self._fail(ctx, [f"could not read the decision: {e}"], outcome.final_text)
        self.log(ctx.run_id, "parse", {"decision": _short(decision)})

        problems = pack.check(ctx, decision, understood)
        self.log(ctx.run_id, "check", {"problems": problems})
        if problems:
            return self._fail(ctx, problems, outcome.final_text)

        acted = [self._call(ctx, c) for c in pack.act(ctx, decision)]
        self.log(ctx.run_id, "act", {"actions": [{"name": a["call"].name, "verdict": a["verdict"]} for a in acted]})
        remembered = pack.remember(ctx, decision, acted)
        self.log(ctx.run_id, "remember", remembered if isinstance(remembered, dict) else {})
        return rt.close_run(ctx, "held" if ctx.held else "done", outcome.final_text)

    def _call(self, ctx, call):
        if isinstance(call, ToolCall):
            name, args = call.name, call.args
        elif isinstance(call, dict):
            name, args = call["name"], call.get("args", {})
        else:
            name, args = call
        return self.runtime.invoke_tool(ctx, name, args)

    def _fail(self, ctx, problems, final_text):
        result = self.runtime.close_run(ctx, "failed", final_text)
        return replace(result, reason="; ".join(problems))


def _short(value, limit=500):
    return str(value)[:limit]
