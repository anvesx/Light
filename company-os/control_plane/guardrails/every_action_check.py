"""Check point 2, every action: runs before and after each tool call, whoever asked for it."""
from contract.plugin_contract import Plugin
from contract.types import ALLOW, Decision

from . import outside_text
from .access_policy import MESSAGE_TARGET_ARG, MESSAGE_TOOL

AREA_ARGS = ("client_id", "area_id")


class ActionGuard(Plugin):
    name = "action_guard"

    def __init__(self, policy, approvals, directory, memory_store=None):
        self.policy, self.approvals, self.directory = policy, approvals, directory
        self.memory_store = memory_store  # where warnings are logged; falls back to the run's store

    def before_tool(self, call, ctx):
        task = ctx.task
        if not self.policy.may_use(task.agent, call.name):
            return Decision("deny", f"tool {call.name!r} is not allowed for agent {task.agent!r}")
        for key in AREA_ARGS:
            if key in call.args and call.args[key] != task.area_id:
                return Decision("deny", f"{key} {call.args[key]!r} is not the task's area {task.area_id!r}")
        if call.name == MESSAGE_TOOL:
            to = call.args.get(MESSAGE_TARGET_ARG)
            if not self.policy.can_message(self.directory, to):
                return Decision("deny", f"{to!r} is not a DevX person: messages go to DevX people only")
        if "client_contact_id" in call.args:
            # A message to a client may only go to a contact of the run's own client.
            who = self.directory.get(call.args["client_contact_id"])
            if not who or who.get("is_devx") or who.get("client_id") != task.area_id:
                return Decision("deny", f"{call.args['client_contact_id']!r} is not a contact of client {task.area_id!r}")
        if self.policy.is_risky(call.name):
            reason = f"{call.name} is a risky action and needs a person's approval"
            approval_id = self.approvals.request(ctx.run_id, task.agent, call.name, call.args, reason)
            ctx.held.append(approval_id)
            return Decision("ask", reason)
        return ALLOW

    def after_tool(self, call, result, ctx):
        if not self.policy.reads_outside_text(call.name):
            return result
        if outside_text.looks_like_instruction(result):
            store = self.memory_store or getattr(ctx.memory, "_store", None)
            if store is not None:
                store.log_step(ctx.run_id, "warning", {"warning": "outside text looks like an instruction",
                                                       "tool": call.name})
        return outside_text.wrap(result, call.name)
