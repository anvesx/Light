"""Runs a risky call once, after a person approved it. Rejected, pending or already-run approvals do nothing."""
from contract.types import RunContext, Task

STEP = "approved_action"


def execute_approved(approval_id, approvals, runtime_tools, memory) -> dict:
    """`runtime_tools` is a ToolRegistry or a dict of name -> ToolSpec; `memory` is the MemoryStore."""
    row = approvals.get(approval_id)
    if row is None:
        return {"status": "skipped", "reason": "unknown approval"}
    if row["status"] != "approved":
        return {"status": "skipped", "reason": f"approval is {row['status']}"}
    run_id = row["run_id"]
    for step in memory.run_steps(run_id):
        if step["step"] == STEP and step["detail"].get("approval_id") == approval_id:
            return {"status": "skipped", "reason": "already run"}
    spec = runtime_tools.get(row["tool"])
    if spec is None:
        return {"status": "skipped", "reason": f"unknown tool {row['tool']!r}"}
    run = memory.get_run(run_id)
    task = Task(agent=row["agent"], caller_id=run["caller_id"], area_id=run["area_id"],
                trigger_kind=run["trigger_kind"])
    ctx = RunContext(run_id=run_id, task=task, memory=memory.scoped([run["area_id"]]))
    try:
        result, status = str(spec.fn(row["args"], ctx)), "ran"
    except Exception as e:  # logged once; it is not retried
        result, status = f"error: {e}", "failed"
    memory.log_step(run_id, STEP, {"approval_id": approval_id, "tool": row["tool"], "args": row["args"],
                                   "approved_by": row["decided_by"], "result": result})
    return {"status": status, "result": result}
