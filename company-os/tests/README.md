# tests

**Role in the harness:** Tests: unit tests for every folder, plus integration tests for the whole system.

A test is a small program that checks one thing and fails loudly if it is wrong. Every folder of the Company OS has tests here. The integration test runs a whole simulated day and the exams runner.

## Run the tests

```
python3 -m unittest discover -s tests -t .     # all tests
python3 -m unittest tests.test_integration -v  # one file
```

Run them from the `company-os` folder. They use only the Python standard library and a fake model, so they cost nothing and give the same result every time.

## Files in this folder

| File | What it does |
|---|---|
| `__init__.py` | Marks the folder as a Python package. |
| `test_agent_finance_watch.py` | Finance watch: a real run, refusals, the salary rule, the check step and the exam. |
| `test_agent_meeting_prep.py` | Meeting prep: full run, access, the check step, injection and the exam. |
| `test_agent_registry.py` | Agent registry: every name imports or has a reason, the builder skips a missing name. |
| `test_company_data.py` | Dummy company: rows exist, builds repeat, every planted case is visible in the data. |
| `test_company_memory.py` | Memory: items by area, links, runs, append-only steps, scoping. |
| `console_stub.py` | A small console stand-in for plug-in page tests (contract C8). |
| `test_connectors.py` | Connectors: directory, meeting sync, memory views, tools, planted signals. |
| `test_contract_conformance.py` | The plugin contract: conformance tests a core must pass. |
| `test_gateway.py` | Gateway: routing, prompt cache, cost ledger, budgets, fake model. |
| `test_guardrail_gate.py` | The guardrail gate: six cases on the real runtime. |
| `test_guardrails.py` | Guardrails: outside text, access policy, way-in check, tool scope, action guard. |
| `test_integration.py` | One demo day (message, held approval, quiet run, refusal) and the exams runner. |
| `test_lifecycle_kit.py` | Lifecycle kit: action tools, approved actions and each runner step. |
| `test_people_surface.py` | People surface: private outbox and approval queue. |
| `test_runtime.py` | Runtime loop: model calls, tools, steps, limits. |
| `test_triggers.py` | Triggers: clock, timer, request, calendar, dispatch. |

Tests of the agents moved to `experiments/` are in `experiments/tests/`. The suite does not run them.
