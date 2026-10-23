# contract

**Role in the harness:** The plugin contract: the 6 functions agent packs and guardrails use to talk to the core. If the core changes (our runtime, or dsh later), plugins do not.

The plugin contract: shared types plus six functions. Nothing else crosses the line between plugins and the core.

Files:
- `types.py`: shared data shapes (`Task`, `ToolSpec`, `ModelRequest`, `RunResult` and others).
- `plugin_contract.py`: `Plugin` (hooks), `Host` (what a core offers), `RunLog` and `WayInGate` (what the core receives from the control plane).
- `conformance_tests.py`: `run_conformance(test_case, make_host)` checks any Host.

The six functions:
- Host: `run_task(task)` runs a task end to end. `add_tool(spec)` registers a tool.
- Hooks a plugin may implement: `before_request` (change the model request), `before_tool` (allow, ask or deny a call),
  `after_tool` (change a tool result), `after_reply` (see the model reply).
The Host also has a kit API (`open_run`, `run_loop`, `invoke_tool`, `close_run`) for the lifecycle kit. It is not a plugin hook.

Why plugins import only the contract: guardrails and agent packs then do not depend on our runtime.
If the core changes (our runtime, or DeepSeek's harness later), the plugins stay the same.

Check a new core: pass `make_host(plugins, gate, replies)` to `run_conformance` inside a `unittest.TestCase`.
`make_host` returns a Host whose model gives `replies` (a list of `ModelReply`) in order. `gate` has `admit(task)`; None allows all.

## Files in this folder

| File | What it does |
|---|---|
| `conformance_tests.py` | Conformance checks for any Host (our runtime, or a dsh adapter later). |
| `plugin_contract.py` | The plugin contract (also `RunLog` and `WayInGate`): the only thing agent packs and guardrails import from the core. |
| `types.py` | Shared data shapes. Every module imports these, so keep them small and stable. |
