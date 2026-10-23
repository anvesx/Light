"""Check point 1, the way in: decides if a task may start at all. Has a global pause switch."""
from contract.types import ALLOW, Decision

from . import role_scopes

SYSTEM_CALLER = "system"
SYSTEM_TRIGGERS = ("timer", "event")


class WayInCheck:
    def __init__(self, directory, gateway, policy, paused=False):
        self.directory, self.gateway, self.policy, self.paused = directory, gateway, policy, paused

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def admit(self, task) -> Decision:
        deny = self._first_problem(task)
        return Decision("deny", deny) if deny else ALLOW

    def _first_problem(self, task):
        if self.paused:
            return "all agents are paused"
        if not self.policy.is_registered(task.agent):
            return f"unknown agent {task.agent!r}"
        if task.caller_id == SYSTEM_CALLER:
            if task.trigger_kind not in SYSTEM_TRIGGERS:
                return "system may only run timer or event tasks"
        else:
            if self.directory.get(task.caller_id) is None:
                return f"unknown caller {task.caller_id!r}"
            role = self.directory.role(task.caller_id)
            if not self.policy.may_start(role, task.agent):
                return f"role {role!r} may not start agent {task.agent!r}"
            if not self._has_area(task.caller_id, task.area_id):
                return f"caller has no access to area {task.area_id!r}"
        if self.gateway.budget_left(task.agent, task.caller_id) <= 0:
            return "budget is spent for this agent or caller"
        return None

    def _has_area(self, caller_id, area_id):
        if area_id in self._areas_of(caller_id):
            return True
        # Any DevX person with a permitted role may use the internal area.
        return area_id == "devx-internal" and bool(self.directory.is_devx(caller_id))

    def _areas_of(self, caller_id):
        if role_scopes.console_role(self.directory, caller_id):
            return role_scopes.readable_areas(self.directory, caller_id)
        return self.directory.client_access(caller_id)

    def extra_read_areas(self, task) -> set:
        """Areas added to the run's memory scope: the library, for a library pack and a caller who may read it."""
        if not self.policy.reads_library(task.agent):
            return set()
        if task.caller_id == SYSTEM_CALLER:
            return {role_scopes.LIBRARY_AREA}
        role = role_scopes.console_role(self.directory, task.caller_id)
        return {role_scopes.LIBRARY_AREA} if role_scopes.may_see(role, "library") else set()
