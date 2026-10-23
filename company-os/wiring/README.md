# wiring

**Role in the harness:** Wiring: builds the whole system the same way for the demo, the console, the exams and the tests.

Builds the whole Company OS in one place: `build_company_os(agents=...)` in `build_company_os.py`.
The demo, the web console, the exams and the agent tests all call it, so every part is wired the same way.

What it does, in order:
1. Opens the dummy company data (builds it if missing).
2. Creates company memory, the outbox and the approval queue in a state folder (a temp folder by default).
3. Creates one memory area per client, plus `devx-internal` and `hold`, and loads past meetings into memory.
4. Loads each agent pack through `agent_registry.py`: `<package>/pack.py` → `make_pack(parts)`, `<package>/fake_brain.py` → `brain(request)`. `agents=None` means every available agent. A name that cannot be imported is skipped.
5. Builds the gateway (fake model, cost ledger, prompt cache), the way-in check, and the runtime with two plugins:
   `ToolScope` (each agent sees only its tools) and `ActionGuard` (the every-action check).
6. Registers each pack's tools and access rules.

Use: `cos = build_company_os(); result = cos.run("meeting_prep", caller_id="P06", area_id="C02", inputs={"event_id": "EV113"})`.

## Files in this folder

| File | What it does |
|---|---|
| `build_company_os.py` | Builds the whole Company OS in one place, so the demo, the console, the exams and the tests all wire it the same way. |
| `agent_registry.py` | The list of agents (name to package), their families and titles, and `available_agents()`. |
