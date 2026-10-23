# experiments

**Role in the harness:** Parked work. The core never imports this folder, and the test run does not include it. Nothing here is deleted.

Version 2 keeps only the finance and meeting prep agents. These five agents and their parts were moved here with `mv`, with file contents unchanged.

## Was at, is now

| Was at | Is now |
|---|---|
| `agents/project_risk/`, `agents/fraud_watch/`, `agents/hiring_forecast/`, `agents/delivery_progress/`, `agents/client_requests/` | `experiments/agents/<same name>/` |
| `connectors/{project_tools,project_hours,store_pos_tools,staffing_tools,git_tools,progress_views,client_request_tools}.py` | `experiments/connectors/` |
| `company_data/generate_git_activity.py`, `company_data/generate_client_requests.py` | `experiments/company_data/` |
| `web_console/progress_page.py`, `web_console/client_requests_page.py` | `experiments/web_console_v1/` |
| Copies of v1 `web_console/{department_scenarios,agent_cards}.py` and `static/console.js` (before the prune) | `experiments/web_console_v1/` |
| `tests/test_agent_{project_risk,fraud_watch,hiring_forecast,delivery_progress,client_requests}.py`, `test_client_request_tools.py`, `test_client_requests_data.py`, `test_git_activity_data.py`, `test_git_tools.py`, `test_progress_views.py` | `experiments/tests/` |
| Cut-out tests of `test_connectors.py`, `test_company_data.py`, `test_web_console.py` | `experiments/tests/test_connectors_moved.py`, `test_company_data_moved.py`, `test_web_console_moved.py` |
| Original versions of tests that were edited, not cut | `experiments/tests/test_web_console_edited_originals.py` and the `ToolAreaTests` class in `test_connectors_moved.py` |

Kept agents were also regrouped: `agents/finance_watch/` is now `agents/finance/watch/`, `agents/spend_advisor/` is `agents/finance/spend_advice/`, and `agents/meeting_prep/` is `agents/meeting_prep/project_brief/`. Agent names did not change.

## Restore one agent

Do these steps from `company-os/`. The five agents share the connector and data parts below.

1. Move the agent back: `mv experiments/agents/<name> agents/<name>`. The pack then needs its own folder path in the registry.
2. Add it to `AGENTS` in `wiring/agent_registry.py`, for example `"project_risk": "agents.project_risk"`, and to a family in `FAMILIES`.
3. Move back the connectors it uses (table below): `mv experiments/connectors/<file>.py connectors/`. Add the tool group back to `connectors/__init__.py` where it was listed (`project_tools`, `staffing_tools`, `store_pos_tools`).
4. Turn its data on in `build()` in `company_data/generate_dummy_data.py`: `git_activity=True` or `client_requests=True`. Move `experiments/company_data/<generator>.py` back to `company_data/`. Rebuild: `python3 -m company_data.generate_dummy_data`.
5. Copy its console page back from `experiments/web_console_v1/` (the page file, its card in `agent_cards.py`, its scenarios and demo in `department_scenarios.py`, its code in `static/console.js`, and the routes in `console_api.py`). Add its tool names back to `TOOL_PLAIN` in `run_walkthrough.py`.
6. Move its tests back: `mv experiments/tests/<file>.py tests/`. Merge the cut-out tests from the `*_moved.py` files into the matching test file, and put the edited tests back from `*_edited_originals.py`.
7. Delete `web_console/state/*.db` and `console_state.json`, then run `python3 -m unittest discover -s tests -t .` and `python3 -m evaluation.run_all_exams`.

| Agent | Connectors | Data flag and generator | Console page | Tests to move back |
|---|---|---|---|---|
| `project_risk` | `project_tools.py`, `project_hours.py` | none (always generated) | none (scenarios and card only) | `test_agent_project_risk.py` |
| `fraud_watch` | `store_pos_tools.py` | none (always generated) | none (scenarios and card only) | `test_agent_fraud_watch.py` |
| `hiring_forecast` | `staffing_tools.py`, `project_hours.py` | none (always generated) | none (scenarios and card only) | `test_agent_hiring_forecast.py` |
| `delivery_progress` | `git_tools.py`, `progress_views.py`, `project_hours.py` | `git_activity=True`, `generate_git_activity.py` | `progress_page.py`, the Project progress page in `console.js` | `test_agent_delivery_progress.py`, `test_git_tools.py`, `test_git_activity_data.py`, `test_progress_views.py` |
| `client_requests` | `client_request_tools.py` | `client_requests=True`, `generate_client_requests.py` | `client_requests_page.py`, the Client requests page in `console.js` | `test_agent_client_requests.py`, `test_client_request_tools.py`, `test_client_requests_data.py` |

The HR department tab and its scenarios (hiring forecast) are in `experiments/web_console_v1/department_scenarios.py`.

## Not moved

The planted cases for these agents are still in `company_data/` and its answer keys. The recorded real-Claude runs in `web_console/real_model_samples.json` and `evaluation/record_real_samples.py` still name the moved agents; X0 does not own them.
