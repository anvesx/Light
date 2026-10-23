"""Fake model for tests and demos. A brain per agent stands in for the model's judgement."""
import json
from dataclasses import replace

from contract.types import ModelReply, ModelRequest, Usage


def _chars(req: ModelRequest) -> int:
    tools = sum(len(t.name) + len(t.description) + len(json.dumps(t.params)) for t in req.tools)
    return len(req.system) + tools + len(json.dumps(req.messages))


class FakeModel:
    def __init__(self, brains: dict):
        self.brains = brains

    def complete(self, req: ModelRequest, agent: str) -> ModelReply:
        reply = self.brains[agent](req)
        out_chars = len(reply.text) + sum(len(json.dumps(c.args)) + len(c.name) for c in reply.tool_calls)
        usage = Usage(input_tokens=_chars(req) // 4, output_tokens=out_chars // 4)
        return replace(reply, usage=usage)
