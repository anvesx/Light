# core

**Role in the harness:** The core harness: the agent loop and the model gateway. It runs one task and talks to a model. It knows nothing about companies, roles or agents.

The core is the small part that stays the same for every product built on it. It must not import `control_plane/`, `agents/`, `lifecycle_kit/`, `web_console/` or `company_data/`. `tests/test_layer_boundary.py` checks this.

The core gets the run log and the way-in gate as objects. They follow `contract.plugin_contract.RunLog` and `WayInGate`. `wiring/build_company_os.py` passes them in.

The clock, the cost ledger and the price table are in the core because the loop and the gateway use them directly.

## Files in this folder

| File | What it does |
|---|---|
| `agent_loop.py` | The loop: runs tool checks, logs every step. Implements the contract's Host. |
| `tool_registry.py` | Holds the tool specs, sorted by name so the cached prefix stays stable. |
| `tool_output_cap.py` | Cuts a tool result so one tool cannot flood the model's context. |
| `compaction.py` | Folds the old middle of a long conversation into one summary. |
| `model_gateway.py` | The only path to a model. Routes by model name, counts cache and cost, enforces budgets. |
| `prompt_cache.py` | Simulated prompt cache: tells whether the system and tools prefix would be a hit. |
| `fake_model.py` | Fake model for tests and demos. A brain per agent stands in for the model. |
| `claude_cli_model.py` | Real model through the `claude -p` CLI. Not called in tests. |
| `cost_ledger.py` | One row per model call, plus budgets per agent or per caller. |
| `model_prices.py` | Price table (USD per million tokens) and the cost of one call. |
| `fixed_clock.py` | A tiny clock. Time moves only when `advance()` is called. |

## Agent loop

Our thin agent runtime. It implements `contract.plugin_contract.Host`, so plugins and agent packs never import it directly.

Files:
- `agent_loop.py`: `Runtime(gateway, memory_store, way_in_gate, plugins=(), max_steps=12, retries=2, clock=None)`.
- `tool_registry.py`: holds tool specs, returns them sorted by name (keeps the cached prefix stable).
- `tool_output_cap.py`: `cap_output` cuts a tool result to 8,000 characters and adds a note.

Flow of `run_task(task)`: `open_run` (way-in gate, start run) -> `run_loop` -> `close_run`.
Each loop step: build request, `before_request`, gateway call (retry `TransientModelError` up to `retries`),
`after_reply`, then for each tool call `before_tool` (deny, ask or allow), run, cap, `after_tool`.
- deny: the tool does not run; the result is `denied: <reason>`.
- ask: the tool does not run; the run ends with status `held`.
- Unknown tool or tool exception: the result is `error: ...`.
Every model call and tool call is written with `memory_store.log_step`.

The lifecycle kit uses `open_run`, `run_loop`, `invoke_tool` and `close_run` to run one task in steps.
`invoke_tool` runs the same hooks as a model tool call.
The memory object needs `start_run`, `log_step`, `end_run`, `scoped`. The way-in gate needs `admit(task) -> Decision`.

## Compaction (`compaction.py`)

`compact_if_needed(messages, *, window_tokens, model_call, threshold=0.8, keep_recent=6)` returns `(messages, CompactionNote | None)`.
- Below `threshold * window_tokens` (estimate: 4 characters per token) it returns the messages unchanged.
- Above it, the first message and the last `keep_recent` messages stay. The cut moves earlier so a tool result keeps its tool call.
- The middle becomes one user message: a summary from `model_call(messages) -> str` plus a code-made list of decision lines, ids and numbers.
- It never touches the system prompt or tool list, so the prompt cache stays valid. Design adapted from dsh (see `THIRD_PARTY_NOTICES.md`).
- If `model_call` raises, the error goes up. The loop is not changed here; I1 adds the hook.

## Gateway

The AI gateway. It is the only path from our code to a model. The runtime holds a `Gateway`, never a backend.

Files:
- `model_gateway.py`: `Gateway`, `BudgetExceeded`, `TransientModelError`.
- `model_prices.py`: price table (USD per million tokens) and `cost_usd(model, usage)`.
- `prompt_cache.py`: `PromptCache` simulates the 5-minute prompt cache; a miss names what changed.
- `cost_ledger.py`: `CostLedger` records every call and holds budgets (`agent:<name>`, `caller:<id>`).
- `fake_model.py`: `FakeModel(brains)`, a deterministic model for tests and demos.
- `claude_cli_model.py`: `ClaudeCliModel`, a real model through `claude -p`. Tests use a fake runner and never call it.
- `fixed_clock.py`: `FixedClock`, a clock that moves only with `advance(minutes)`.

Use:
```python
gw = Gateway({"fake": FakeModel({"my_agent": brain})})
gw.ledger.set_budget("agent:my_agent", 1.00)
reply = gw.call(req, agent="my_agent", caller_id="P01", area_id="C01", run_id="r1")
```
A backend is any object with `complete(req, agent) -> ModelReply`. The gateway picks it by `req.model`.
`input_tokens` in the ledger is the uncached part only. Cache read and write tokens are priced separately.

## Use a real model

Any agent can run with a real Claude model. Only the gateway backend changes.
```python
cos = build_company_os(real_model="claude-cli")           # registers ClaudeCliModel under "claude-cli"
cos.run("finance_watch", "P07", "devx-internal", model="claude-cli")
```
- It calls `claude -p --output-format json --model sonnet` and uses the person's own Claude plan. No API key is read.
- The prompt holds the system text, the tool list (JSON schema) and the conversation. The model must answer with JSON: `{"tool_calls": [...]}` or `{"final": "<text>"}`.
- A reply that cannot be read gets one retry with the parse error. A timeout, a non-zero exit or a second bad reply raises `TransientModelError`, and the runtime retries.
- Usage comes from the CLI. If the CLI gives none, it is estimated as characters / 4 (`ClaudeCliModel.estimated_calls` counts these).
- Cost is priced as `sonnet-5-5` (the `claude-cli` alias in `model_prices.py`).
- Tests pass a fake `runner=`, so they never start the CLI.
- Vertex (or any other host) would be one more backend of the same shape: a class with `complete(req, agent)`, passed in `extra_backends`.
