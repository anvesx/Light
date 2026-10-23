"""Base class for an agent pack. A pack fills in the lifecycle steps; the runner calls them in order."""


class AgentPack:
    name = "agent"
    starter_roles = frozenset()    # roles that may start this agent
    approver_roles = frozenset()   # roles that may approve its risky actions
    reads_library = False          # True: the run may also read the `playbooks` area (if the caller may)

    def tools(self) -> list:
        return []

    def system_prompt(self) -> str:
        return ""

    def record(self, ctx):
        """Collect the facts for this run (read tools, memory). Returns anything `understand` needs."""
        return None

    def understand(self, ctx, recorded) -> dict:
        """Turn the facts into a dict. Empty, or {"quiet": True}, means nothing to do: no model call."""
        return {}

    def decision_prompt(self, understood) -> str:
        return ""

    def parse_decision(self, final_text) -> dict:
        raise NotImplementedError

    def check(self, ctx, decision, understood) -> list:
        """Return a list of problems. Any problem stops the run before it acts."""
        return []

    def act(self, ctx, decision) -> list:
        """Return the tool calls to make: ToolCall objects, {"name", "args"} dicts or (name, args) tuples."""
        return []

    def remember(self, ctx, decision, acted):
        """Optional. May return a dict that the runner logs."""
        return None

    def register(self, runtime, policy):
        specs = self.tools()
        for spec in specs:
            runtime.add_tool(spec)
        policy.note_tool_specs(specs)
        policy.register_agent(self.name, {s.name for s in specs}, self.starter_roles, self.approver_roles,
                              reads_library=self.reads_library)
