# Plan: running agents 24/7

Written Oct 21, 2026. Status: plan only. Nothing here is built, except what the "Today" column says.

## 1. Goal

The core harness and the company brain work. To run all day with nobody watching, the control plane needs more. An agent that runs at 3 AM has no person next to it. So the control plane must keep cost low, stop an agent at once and recover after a crash. It must also let an agent do more only when it has earned it.

All the ideas below live in the control plane. The core harness does not change.

## 2. The eight ideas

| # | Idea | Why it matters | Today (confirmed in code) | What we add |
|---|---|---|---|---|
| 1 | Cost comes first | A 24/7 agent can spend money all night | Every model call is metered in `core/cost_ledger.py`. A spent budget per agent or per person stops the call (`core/model_gateway.py:31`). An unknown model is refused (`core/model_prices.py`) | A cheap model (Haiku) tries first. A check decides if the task goes up to Sonnet. Never Opus. Track the cost of each useful result, not only the total |
| 2 | A stop switch that works mid-run | One bad agent must stop at once | A global pause blocks new runs (`control_plane/guardrails/way_in_check.py`). A run that has started does not stop | Check the switch before every action too. Add a pause for each agent |
| 3 | Runs survive a crash | A server restarts. A run must not be lost or do the same thing twice | The run log keeps every step. A run cannot resume | Save after each step and resume from there. Each write has a key, so a repeated write has one effect. A run can wait days for an approval |
| 4 | Always on | Agents must wake on events, not when someone runs a script | Triggers run on a simulated clock (`control_plane/triggers/simulated_clock.py`) | A server with a scheduler, webhooks, a job queue with retries, and a watchdog that alerts a person. Agents that browse run in one cloud VM per user, one box per agent (`docs/research/per-user-vms.md`) |
| 5 | Autonomy is earned | Trust should follow results | Fixed in code: risky tools always ask a person (`is_risky`) | Three levels (section 4). An agent moves up only on measured results. It moves down by itself after a serious mistake |
| 6 | Undoable or not | The safest rule is about undo, not about which agent acts | Risky tools are listed by hand | Mark every action as undoable or not. Undoable actions inside the rules run at once. The rest wait for a named person. Approvals expire |
| 7 | Release gate | A change can make an agent worse, and nobody would notice | 10 exams, run by hand before a commit | A change goes live only if its exams pass 3 times in a row. Then the agent runs in shadow on real data before it may act |
| 8 | Every failure becomes a test | The same mistake should never come back | Corrections are stored. The learning loop is designed, not built | Each correction or failed run becomes a rule and an exam case. We count whether it comes back |

## 3. The path of one 24/7 run

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ Events       │   │ Job queue    │   │ Way-in check │   │ The run      │   │ Every-action │
│ (outside)    │──►│ (planned)    │──►│ (built; add  │──►│ (core)       │──►│ check (built;│
│ new Fathom   │   │ each job     │   │  levels)     │   │ saves after  │   │  add levels) │
│ recording,   │   │ runs once,   │   │ stop switch, │   │ each step,   │   │ undoable?    │
│ timer, a     │   │ retries with │   │ budget left, │   │ resumes after│   │ inside its   │
│ person asks  │   │ waits        │   │ agent level  │   │ a crash      │   │ level?       │
└──────────────┘   └──────────────┘   └──────────────┘   └──────▲───────┘   └──────┬───────┘
                                                                │                  ▼
                                      ┌─────────────────────────┴───┐       ┌──────────────┐
                                      │ Watchdog (planned)          │       │ People       │
                                      │ finds a stuck or failed run │       │ approve or   │
                                      │ and alerts a person         │       │ reject;      │
                                      └─────────────────────────────┘       │ approvals    │
                                                                            │ expire       │
                                                                            └──────────────┘
```

## 4. Autonomy levels

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│ Level 0: Shadow  │     │ Level 1: Suggest │     │ Level 2: Act     │     │ NEVER AUTOMATIC  │
│ every new agent  │────►│ writes letters   │────►│ small, undoable  │     │ at any level     │
│ starts here;     │     │ and proposals;   │     │ actions, inside  │     │ payments,        │
│ runs on real     │     │ a person does    │     │ its spend limit; │     │ bookings, client │
│ data, no action  │     │ every action     │     │ all logged       │     │ emails wait for  │
└──────────────────┘     └──────────────────┘     └──────────────────┘     │ a named person   │
        moves up only on measured results ────►                            └──────────────────┘
```

- **Moving up.** The agent must be no worse than a trained person on the same task, over at least 50 reviewed runs. This number is a starting value, not a measurement.
- **Moving down.** One serious mistake, or a rising error rate, drops the agent one level at once.
- **An owner for each agent.** A named person answers for each agent and its limits.

## 5. Rules that never change

- An agent can never change its own exams, budget, level or stop switch.
- An action that cannot be undone always waits for a named person.
- Learning stays inside the company. Lessons come from our runs and stay in our memory.
- Two tests prove the safety:
  - **Planted problems.** We hide 10 known problems. The agents must raise each one before a person does.
  - **Planted secret.** A fake secret in a document must never appear in a model call, a log or a letter.

## 6. Build order

1. The stop switch before every action, and cheap-first models. Small changes, a big safety gain.
2. The server: scheduler, webhooks, job queue, crash resume and watchdog.
3. The release gate, and the planted-problem and planted-secret tests.
4. Undoable marks and autonomy levels, with approvals through Slack.
5. Failures become tests. Then the learning loop.

## 7. Open questions

| Question | Our suggestion |
|---|---|
| Which actions count as undoable? | Start with: create a task, send an internal reminder |
| What result lets an agent move up a level? | No worse than a trained person, over at least 50 reviewed runs |
