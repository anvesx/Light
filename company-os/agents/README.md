# agents

**Role in the harness:** The agent packs: each pack is one job an agent does for one group of people, built on the shared lifecycle kit.

An agent here is a small package that watches one part of the company and tells the right people in a private message. Each pack fills in the same steps (record, understand, decide, check, act, remember) and declares its tools and who may start it. The shared guardrails then apply to every pack the same way. No pack changes anything without a person's approval.

Each pack folder has its own README with the details. Exam results below come from `python3 -m evaluation.run_all_exams`.

| Pack | Watches | Tells | Exam result |
|---|---|---|---|
| `meeting_prep` (`meeting_prep/project_brief/`) | Open questions, tasks and decisions from past meetings with a client | The DevX people on the meeting invite (brief) | 93% of askable topics covered, injection blocked |
| `finance_watch` (`finance/watch/`) | DevX's invoices, payments, budgets and travel spend | The finance lead, and the CEO for travel | 8 of 8 found, 0 false alarms |

### Spend advisor (`finance/spend_advice/`)
Answers the CEO's and finance lead's spending questions at any time: cost by category, travel's share, and a verdict for every trip (best option chosen, or how much a cheaper option would have saved), with simple policy suggestions. Exam: 9 of 9 planted savings found, 0 false alarms.

## Files in this folder

| File or subfolder | What it does |
|---|---|
| `__init__.py` | Marks the folder as a Python package. |
| `meeting_prep/project_brief/` | Meeting prep pack: pack, fake brain, replay exam, README. |
| `finance/watch/` | Finance watch pack: pack, fake brain, replay exam, README. |
| `finance/spend_advice/` | Spend advisor: spending questions, trip verdicts and savings, for the CEO and finance lead. |

The agent names stay `meeting_prep`, `finance_watch` and `spend_advisor`. `wiring/agent_registry.py` maps each name to its folder. The other agents moved to `experiments/agents/`.
