# Tickets: what runs in parallel, what waits

The build is split into tickets. Tickets in the same wave do not depend on each other, so they run at the same time (one Sonnet agent each). A wave starts only when the wave before it is done and its tests pass.

```
 Wave 0 (lead)        Wave 1 (parallel)          Wave 2 (parallel)        Wave 3 (parallel)          Wave 4 (lead)
 ┌──────────────┐     ┌────────────────────┐     ┌───────────────────┐    ┌──────────────────────┐    ┌──────────────┐
 │ T0 spec,     │────►│ T1 company data    │────►│ T5 connectors     │───►│ T6 meeting prep      │───►│ T10 demo,    │
 │ shared types,│     │ T2 gateway+runtime │────►│ T4 guardrails +   │───►│ T7 project risk      │    │ all exams,   │
 │ contract     │     │ T3 memory, people  │────►│    lifecycle kit  │    │ T8 finance watch     │    │ results      │
 └──────────────┘     │    surface,triggers│     └───────────────────┘    │ T9 fraud watch       │    └──────────────┘
                      └────────────────────┘                              └──────────────────────┘    ┌──────────────┐
                                                                                                         │ T11 web      │
                                                                                                         │ console      │
                                                                                                         └──────────────┘
```

| Ticket | Wave | Builds | Needs | Folder(s) | Status |
|---|---|---|---|---|---|
| T0 | 0 | Spec, shared types, plugin contract, folder skeleton | nothing | `SPEC.md`, `contract/types.py`, `contract/plugin_contract.py` | done |
| T1 | 1 | Dummy company systems and planted cases | T0 | `company_data/` | done, 24 tests pass; HR person P90 added |
| T2 | 1 | AI gateway (prompt cache, cost ledger, fake model), runtime loop, contract conformance tests | T0 | `gateway/`, `runtime/`, `contract/conformance_tests.py` | done, 27 tests pass |
| T3 | 1 | Company memory, people surface (outbox, approvals), triggers | T0 | `company_memory/`, `people_surface/`, `triggers/` | done, 37 tests pass |
| T4 | 2 | Guardrails (way-in, every-action, outside text) and the lifecycle kit; six-case guardrail gate test | T2, T3 | `guardrails/`, `lifecycle_kit/` | done, 52 tests pass |
| T5 | 2 | Connectors: people directory, meetings into memory, read tools | T1, T3 | `connectors/` | done, 44 tests pass |
| T6 | 3 | Meeting prep agent and its replay exam | T4, T5 | `agents/meeting_prep/` | done; exam: 93% of askable topics covered, injection blocked |
| T7 | 3 | Project risk agent and its replay exam | T4, T5 | `agents/project_risk/` | done; exam: 4 of 4 found, 0 false alarms, 0 days late |
| T8 | 3 | Finance watch agent and its exam | T4, T5 | `agents/finance_watch/` | done; exam: 8 of 8 found, 0 false alarms |
| T9 | 3 | Fraud watch agent and its exam | T4, T5 | `agents/fraud_watch/` | done; exam: 3 of 3 found, 0 false alarms |
| T12 | 3 | Hiring forecast agent (for HR): allocation and won pipeline against team capacity; and its exam | T4, T5 | `agents/hiring_forecast/` | done; exam: 2 of 2 team calls agree |
| T5b | 2 | Shared wiring (`build_company_os`) and guarded reads for packs, by the lead | T1 to T5 | `wiring/`, `lifecycle_kit/lifecycle_runner.py` | done |
| T10 | 4 | Demo run, all exams, full test run, results and learnings | all | `run_demo.py`, `evaluation/`, `RESULTS.md` | done |
| T11 | 4 | Working local web console for every department (growth, HR, finance, delivery, CTO): "view as" switch, inbox per person, run or ask an agent, approve or deny, next-day button, runs step by step with cost and guardrail verdicts, agent cards in plain language, memory browser, a guided "try it" path | T6 to T9, T12 | `web_console/` | in progress |

| T13 | 5 | Dummy git activity: repos, PRs linked to tasks and SOW scope items, deploys; planted unbilled work, rework, behind-deadline | T1 | `company_data/generate_git_activity.py` | done; 287 PRs, 210 deploys, 92 scope items |
| T14 | 5 | Delivery progress agent: PR-merge and daily triggers, scope burn-down per project into central memory; flags unbilled work, rework, behind deadline; exam | T13, T5 | `connectors/` (git tools), `agents/delivery_progress/` | done; exam 3 of 3, 0 false alarms |
| T15 | 5 | Project progress feed in central memory with one view per role (CSM, CTO, HR team-level, growth) | T14 | `connectors/progress_views.py` (folded into T14) | done |
| T16 | 5 | Dummy client requests data: blocked tasks, asks, replies, grants; planted: asked twice, stuck 9 days, granted but not working | T13 | `company_data/generate_client_requests.py` | done; 47 requests, 216 events, 4 planted cases |
| T17 | 5 | Client requests agent: kickoff checklist at SOW signing, one-line requests from developers, daily batched asks with steps, reminders and escalation, access checks, blocked days; exam | T16, T5 | `connectors/` (request tools), `agents/client_requests/` | done; exam 4 of 4, 0 secret leaks |
| T18 | 5 | Console pages: Project progress (role views) and Client requests (board, developer request form); CSM page updated | T11, T15, T17 | `web_console/` | done; permission-aware views |

| T19 | 5 | Console redesign to `web_console/DESIGN.md`: agents as colleagues, letters, run stories, drawer, light and dark | T11 | `web_console/` | done; light mode by default |

| T20 | 5 | Real-model path through the gateway (`claude -p`), and real Claude samples recorded once per agent for the console | T11, all agents | `gateway/`, `wiring/`, `evaluation/`, `web_console/` | done; 7 real samples recorded |

| T21 | later | Learning loop: feedback, lessons from every mistake and right step, lessons read before deciding, readiness gate | all | `learning/` (planned) | design ready, not built (on request) |

## How this maps to the 12-week plan

| Plan (harness-decision page, tab 8) | Here |
|---|---|
| Weeks 1 to 2: runtime v1, contract and tests, gateway, way-in check, memory v1, triggers v1 | T2, T3, T4 (way-in part) |
| Week 3: lifecycle kit, every-action checks, connectors | T4, T5 |
| Week 4: first agent pack and replay exam | T6 (meeting prep) |
| Weeks 7 to 12: second agent | T7 (project risk); T8 and T9 test that the kit fits other domains |
| Week 6 tests and guardrail gate | T2 conformance tests, T4 gate test, T10 report |

In the plan, the agents come one at a time. Here all four are built in one wave on dummy data, to test early whether the shared parts really fit four different jobs.
