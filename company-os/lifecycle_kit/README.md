# lifecycle_kit

**Role in the harness:** The lifecycle kit: the steps every agent follows (record, understand, decide, check, act, remember), so each agent pack only fills in its own logic.

The shared lifecycle every agent pack follows, so the guardrails apply the same way to every agent.

Files:
- `agent_pack.py`: base `AgentPack` (steps, `starter_roles`, `approver_roles`, `register(runtime, policy)`).
- `action_tools.py`: `make_send_private_message(outbox)` (not risky) and `make_create_followup_task(memory_store)` (risky).
- `approved_actions.py`: `execute_approved(approval_id, approvals, runtime_tools, memory)` runs an approved call once.
- `lifecycle_runner.py`: `LifecycleRunner(runtime).run(pack, task) -> RunResult`.

Step order (each step is logged with `log_step`):
1. open_run: the way-in check. A refused task stops here.
2. record: the pack collects facts.
3. understand: the pack turns facts into a dict. If it is empty or has `"quiet": True`, the runner logs "quiet",
   closes the run as "done" and makes no model call.
4. decide: `runtime.run_loop` with the pack prompt plus the outside-text rule.
5. parse: read the model's JSON answer.
6. check: the pack lists problems. Any problem closes the run as "failed" with the reasons.
7. act: each action goes through `runtime.invoke_tool`, so the every-action check applies.
8. remember, then close_run ("held" if an action waits for approval).

Check comes before act because an action can reach a person or change memory, and that cannot be taken back.
A bad decision must stop while it is still only text.

Packs read data in `record` and `understand` with `ctx.notes["invoke_tool"](name, args)`. It returns `{"call", "result", "verdict"}`, and the read goes through the same checks and audit log as any action.

## Files in this folder

| File | What it does |
|---|---|
| `action_tools.py` | Action tools every pack may use. Each factory takes what the tool writes to and returns a ToolSpec. |
| `agent_pack.py` | Base class for an agent pack. A pack fills in the lifecycle steps; the runner calls them in order. |
| `approved_actions.py` | Runs a risky call once, after a person approved it. Rejected, pending or already-run approvals do nothing. |
| `lifecycle_runner.py` | Runs one task through the lifecycle: record, understand, decide, check, act, remember. |
