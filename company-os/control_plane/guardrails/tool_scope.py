"""Shows the model only the tools its agent is registered for, sorted by name (keeps the cached prefix stable)."""
from dataclasses import replace

from contract.plugin_contract import Plugin


class ToolScope(Plugin):
    name = "tool_scope"

    def __init__(self, policy):
        self.policy = policy

    def before_request(self, req, ctx):
        allowed = self.policy.tools_of(ctx.task.agent)
        return replace(req, tools=sorted((t for t in req.tools if t.name in allowed), key=lambda t: t.name))
