# guardrails

**Role in the harness:** Guardrails: the two check points. The way-in check runs before any run starts; the every-action check runs on every tool call, read or write.

Two check points keep every agent inside its rules. Packs never skip them: the runtime calls both.

1. **Way in** (`way_in_check.py`): `WayInCheck(directory, gateway, policy, paused=False).admit(task)` runs once, before a run starts.
   It refuses when: paused; unknown agent or caller; the caller's role may not start the agent; no access to the task's area;
   no budget left. The `"system"` caller may run only `timer` and `event` tasks. `pause()` / `resume()` is the global switch.
2. **Every action** (`every_action_check.py`): `ActionGuard(policy, approvals, directory)` is a plugin that checks each tool call.
   It denies tools the agent is not registered for, a `client_id` / `area_id` argument outside the task's area, and messages
   to people who are not DevX. Risky tools return "ask": an approval is created and its id goes to `ctx.held`.
   After a tool runs, results of `reads_outside_text` tools are wrapped as data, and a warning step is logged if they look like orders.

Roles: for Admin, CSM and Growth the way-in check uses `role_scopes.readable_areas`. A pack with `reads_library = True` gets the `playbooks` area added to its run (`WayInCheck.extra_read_areas`) only when the caller may read the library, or is `system`.

Other files:
- `access_policy.py`: `AccessPolicy`, filled when a pack is installed (`register_agent`), never by the model.
- `tool_scope.py`: `ToolScope` plugin, so a model sees only its own agent's tools.
- `outside_text.py`: `wrap`, `looks_like_instruction`, and `RULE` (one sentence every pack adds to its system prompt).

Wire-up: `Runtime(gateway, memory, WayInCheck(...), plugins=[ToolScope(policy), ActionGuard(policy, approvals, directory)])`.

## Files in this folder

| File | What it does |
|---|---|
| `access_policy.py` | Who may start which agent, which tools each agent may use, which tools are risky, who may get messages. |
| `every_action_check.py` | Check point 2, every action: runs before and after each tool call, whoever asked for it. |
| `role_scopes.py` | The role matrix (Admin, CSM, Growth): pages, data kinds, readable memory areas. The way-in check and the run's memory scope use it. |
| `outside_text.py` | Outside text (client files, Slack, transcripts) is data. This file marks it and spots orders hidden in it. |
| `tool_scope.py` | Shows the model only the tools its agent is registered for, sorted by name (keeps the cached prefix stable). |
| `way_in_check.py` | Check point 1, the way in: decides if a task may start at all. Has a global pause switch. |
