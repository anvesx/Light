"""LiveSession: one guarded run per call. Lines are checked by code; the model writes only the end summary."""
import json
import time

from control_plane.company_brain.topic_lexicon import load_lexicon
from contract.types import RunResult, Task
from control_plane.guardrails import role_scopes

from .pack import INSTRUCTIONS, SYSTEM, CONTEXT_MARKER, lines_for_listener, load_call, summary_context


class Refused(Exception):
    """The call could not start. The message is a plain reason."""


class LiveSession:
    def __init__(self, cos, ctx, call, listener, caller_id, model):
        self.cos, self.ctx, self.call, self.listener = cos, ctx, call, listener
        self.caller_id, self.model = caller_id, model
        self.script = {l["line_no"]: l for l in lines_for_listener(call)}
        self.heard, self.suggestions, self.ended = {}, [], None
        self.timings_ms = []

    @property
    def run_id(self):
        return self.ctx.run_id

    @classmethod
    def start(cls, cos, caller_id, call_id, model="fake"):
        from control_plane.connectors.live_call_tools import load_call as find_call
        found = find_call(cos.data_conn, call_id)
        if found is None:
            raise Refused("That call does not exist.")
        role = role_scopes.console_role(cos.directory, caller_id)
        if role != "admin" and caller_id != found["viewer_id"]:
            raise Refused("You can only join your own calls.")
        task = Task(agent="live_copilot", caller_id=caller_id, area_id=found["area_id"], trigger_kind="request",
                    inputs={"call_id": call_id}, model=model)
        ctx = cos.runtime.open_run(task)
        if isinstance(ctx, RunResult):
            raise Refused(ctx.reason or "The way-in check refused this call.")
        rt = cos.runtime
        ctx.notes["invoke_tool"] = lambda name, args: rt.invoke_tool(ctx, name, args)
        call, listener = load_call(ctx.notes["invoke_tool"], call_id, load_lexicon())
        if call is None:
            rt.close_run(ctx, "failed", str(listener))
            raise Refused(str(listener))
        return cls(cos, ctx, call, listener, caller_id, model)

    def hear(self, line_no=None, text=None):
        if line_no is not None and line_no in self.heard:
            return self.heard[line_no]
        began = time.perf_counter()
        if line_no is not None:
            line = self.script.get(line_no)
            if line is None:
                raise ValueError(f"the call has no line {line_no}")
        else:
            if not str(text or "").strip():
                raise ValueError("give a line number or some text")
            line = {"line_no": self._next_no(),
                    "t_sec": 0, "speaker": "Client", "speaker_id": "X00", "lang": "en", "text": str(text).strip()}
        suggestions = self.listener.hear(line)
        reply = {"line_no": line["line_no"], "speaker": line["speaker"], "speaker_id": line["speaker_id"], "text": line["text"],
                 "clean_text": self.listener.clean_text(line), "topics": self._topics(line), "suggestions": suggestions}
        self.timings_ms.append((time.perf_counter() - began) * 1000)
        self.heard[line["line_no"]] = reply
        self.suggestions += suggestions
        for s in suggestions:
            self.cos.memory.log_step(self.run_id, "suggestion", s)
        return reply

    def _next_no(self):
        return max([*self.script, *self.heard], default=0) + 1

    def _topics(self, line):
        from control_plane.company_brain.topic_lexicon import topics_in
        return topics_in(f"{line['text']} {self.listener.clean_text(line)}", self.listener.lexicon)

    def end(self):
        if self.ended:
            return self.ended
        lines = [self.heard[n] for n in sorted(self.heard)]
        context = summary_context({**self.call, "lines": [
            {"line_no": h["line_no"], "speaker": h["speaker"], "clean_text": h["clean_text"]} for h in lines]}, self.suggestions)
        decision = {}
        if lines:
            outcome = self.cos.runtime.run_loop(self.ctx, INSTRUCTIONS + CONTEXT_MARKER + json.dumps(context, separators=(",", ":")),
                                                system=SYSTEM)
            try:
                start, stop = outcome.final_text.find("{"), outcome.final_text.rfind("}")
                decision = json.loads(outcome.final_text[start:stop + 1])
            except ValueError:
                decision = {}
        if not decision.get("summary"):
            decision = {"summary": f"{len(lines)} lines heard, {len(self.suggestions)} suggestion(s).", "next_steps": []}
        source_id = self._save_source(lines)
        result = self.cos.runtime.close_run(self.ctx, "done", json.dumps(decision))
        self.ended = {"run_id": result.run_id, "status": result.status, "summary": decision["summary"],
                      "next_steps": decision.get("next_steps", []), "suggestions": self.suggestions, "source_id": source_id}
        return self.ended

    def _save_source(self, lines):
        brain = self.cos.brain
        if brain is None or not lines:
            return None
        rows = [{"line_no": h["line_no"], "speaker": h["speaker"], "text": h["text"], "lang": None} for h in lines]
        return brain.add_source(self.call["area_id"], "live_call", self.call["title"], "\n".join(r["text"] for r in rows),
                                origin_ref=f"{self.call['call_id']}-live-{self.run_id}", occurred_at=self.cos.clock.now,
                                participants=[{"name": self.call["client_name"], "email": ""}], language="mixed", lines=rows)
