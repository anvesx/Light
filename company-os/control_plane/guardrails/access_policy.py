"""Who may start which agent, which tools each agent may use, which tools are risky, who may get messages."""

MESSAGE_TOOL = "send_private_message"
MESSAGE_TARGET_ARG = "to_person_id"


class AccessPolicy:
    def __init__(self):
        self._agents = {}
        self._specs = {}

    def register_agent(self, agent, tools, starter_roles, approver_roles, reads_library=False):
        """Called when an agent pack is installed, never by the model."""
        self._agents[agent] = {"tools": set(tools), "starters": set(starter_roles),
                               "approvers": set(approver_roles), "library": bool(reads_library)}

    def note_tool_specs(self, specs):
        for s in specs:
            self._specs[s.name] = s

    def is_registered(self, agent):
        return agent in self._agents

    def tools_of(self, agent) -> set:
        return set(self._agents.get(agent, {}).get("tools", ()))

    def may_use(self, agent, tool) -> bool:
        return tool in self.tools_of(agent)

    def reads_library(self, agent) -> bool:
        return bool(self._agents.get(agent, {}).get("library"))

    def may_start(self, role, agent) -> bool:
        return role in self._agents.get(agent, {}).get("starters", ())

    def may_approve(self, role, agent) -> bool:
        return role in self._agents.get(agent, {}).get("approvers", ())

    def is_risky(self, tool) -> bool:
        spec = self._specs.get(tool)
        return True if spec is None else bool(spec.risky)  # unknown spec: treat as risky

    def reads_outside_text(self, tool) -> bool:
        spec = self._specs.get(tool)
        return bool(spec and spec.reads_outside_text)

    def can_message(self, directory, to_person_id) -> bool:
        """Messages may go to DevX people only."""
        return bool(directory.is_devx(to_person_id))
