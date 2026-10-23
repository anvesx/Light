# Results: what the Company OS prototype taught us

Built Oct 18, 2026, from the plan in `../agent-harness/harness-decision/harness-decision.html`. Everything runs on dummy company data. The model is a deterministic fake brain by default; each agent was also run once with real Claude.

**Short answer: the plan holds.** Our own thin runtime, guardrails at two check points, one company memory and small agent packs on one lifecycle kit all worked for seven different jobs. The build found six changes the plan needs, listed in section 3.

## 1. What was built

| Part | Folder | Result |
|---|---|---|
| Dummy company: people, 8 projects, SOWs, 112 meetings, Slack, books, store POS, code history, client requests, planted cases with an answer key | `company_data/` | Done |
| Our own runtime: loop, tool registry, output cap, retries, run log | `core/` | Done; small (about 150 lines) |
| AI gateway: prompt cache, cost ledger, budgets, fake model, real Claude through the `claude` CLI | `core/` | Done; real Claude tested end to end |
| 6-function contract and conformance tests (a dsh adapter would run the same tests) | `contract/` | Done |
| Guardrails: way-in check, every-action check, per-agent tool scope, outside text as data, pause switch | `control_plane/guardrails/` | Done |
| Company memory: one area per client, append-only run log, cases, scores | `control_plane/company_memory/` | Done |
| Triggers: timer, calendar, a person asking | `control_plane/triggers/` | Done |
| Lifecycle kit: record, understand, decide, check, act, remember; quiet runs make no model call | `lifecycle_kit/` | Done |
| Eight agent packs | `agents/` | Done, all exams pass |
| Web console for each department, permission-aware | `web_console/` | Done |
| Tests | `tests/` | 435 pass |

### Exam results (fake brain, replayed day by day)

| Agent | For | Result |
|---|---|---|
| Meeting prep | Growth, CSMs | 93% of topics that were askable were asked; 62% of all decided topics (the rest were surprises nobody could ask about); hidden instruction blocked |
| Project risk | CSMs | 4 of 4 planted problems found on the first possible day; 0 false alarms |
| Finance watch | Finance | 8 of 8 found; 0 false alarms |
| Store watch | Retail client's CSM | 3 of 3 found; 0 false alarms (one found 5 days late: it waits for 2 self-approved discounts) |
| Hiring forecast | HR, CEO | 2 of 2 team calls agree with a separate check from the raw data |
| Delivery progress | CSMs, CEO | 3 of 3 found (unbilled work, rework, behind deadline); 0 false alarms |
| Client requests | Developers, CSMs | 4 of 4 handled (duplicate ask, stuck 9 days, failed access check, password pasted in chat); 0 secret leaks |
| Spend advisor | CEO, finance lead | 9 of 9 planted savings found (late bookings, business seats on short flights, same-city trips, hotels above city rate), 0 false alarms; a verdict for every trip, including "the best option was chosen" |

**These scores test the harness, the data and the checks, not the model's judgement.** The fake brain is code written by us.

## 2. What we learned

1. **The harness is small; the shared parts are the value.** The runtime is about 150 lines. The work went into guardrails, company memory, connectors and checks, which we would need on any core. This supports writing our own thin base.
2. **Check must come before act.** The plan's lifecycle put "act" before "check". Anything that reaches a person must be checked first. The kit runs record, understand, decide, check, act, remember.
3. **Code finds, the model explains.** Every agent finds its problems in plain code; the model only writes the explanation and next step. Quiet days make no model call at all (the demo day: 7 model calls for 9 timer runs). Cost stays low and results stay exact.
4. **Real Claude writes better, and the checks still hold.** With real Claude the steps and checks were unchanged and every run passed its checks. The letters were sharper: meeting prep put the important open questions first with "agree a firm date" asks, where the fake brain listed tasks by date. A run takes 15 to 40 seconds.
5. **Guardrails must sit above the contract, not inside the runtime,** so they work on any core. The way-in check is required by the runtime constructor, so nothing can start a run without it. Agents read data through the same checked path as actions, so every read is in the audit log.
6. **Replays need data "as of" a date.** Without it an exam silently sees the future. Every connector tool and memory view takes an `as_of` date, and item status comes from links up to that date.
7. **Client areas hide patterns across clients.** One person overloaded on two clients' projects is invisible inside either client's area. People-level signals need their own carefully limited area.
8. **Agents must not repeat themselves.** A daily agent repeated the same flag every day until we added "already told" rules (delivery progress and client requests have them; the others do not yet).
9. **People should only see what they may do.** Showing a run that the guardrails then refuse confused people. The console now asks the guardrails what each person may do and shows only that; the refusal stays as a safety net.
10. **CSMs need business words, not code words.** Progress is worked out from merged PRs, but letters and pages show scope items, tasks and percentages. The check step now stops any letter that says "PR", "merged" or "feat:".

## 3. Changes the plan needs

| # | Change | Why |
|---|---|---|
| 1 | Lifecycle order: check before act | Learning 2 |
| 2 | Add a **learning loop** to the base: feedback buttons, lessons from every mistake and right step, agents read recent lessons before deciding, a readiness gate where trust grows with approvals | Rachit's features "learn on its own" and "prevent repeated failures" were planned but never turned into a design. dsh does not have one either (its feedback is never shown to the model). Design ready as ticket T21; not built, on request |
| 3 | An "already told" rule in the kit for every agent | Learning 8 |
| 4 | A limited people-level area for signals that cross clients | Learning 7 |
| 5 | Real connectors read from existing tools (for example DevX's employee console for bandwidth, ClickUp for tasks) instead of copying their data | Avoid duplicating tools people already use |
| 6 | Move savings rules into a travel policy file owned by finance (late = 3 days, earlier fare at least 30% cheaper, economy under 2.5 hours, same city within 7 days, hotel 10% over city rate) | Today they are constants in `control_plane/connectors/spend_tools.py`; they are company policy, not code |
| 7 | A travel booking agent: a person asks for flights for N people; it searches approved travel APIs, ranks by policy, shows the best 3, and booking waits for a manager's approval | The spend advisor only looks back; this books well in the first place. Needs a travel API account (not chosen) |
| 8 | A hidden fare scout that records cheaper fares and hotels from travel APIs, before and after each trip | In the prototype these options are simulated data |
| 9 | A central "chief of staff" agent that answers broad questions by calling other agents as helpers, each in its own fresh context, returning short summaries | Keeps the central context small and the prompt cache stable; every helper call is a normal run with the same guardrails |
| 10 | Only when an agent browses the open web, books or pays, or runs code: a relay sandbox. For a first travel search on one fixed, read-only travel API, simpler steps are enough (host fixed in code, server-side read-only key, response parsed into fixed fields, one egress rule in the container). The relay sandbox: the tool runs in a locked-down process with no database, files or secrets; all traffic goes through a relay that allows only approved hosts and holds the API keys; results are size-capped and marked as outside text; booking has a separate relay behind approval; if the relay is down the tool fails closed | Our guardrails control what an agent may ask for, inside one Python process; they do not physically stop network or disk access. Idea from the Enigma Ticket Desk relays, and our earlier macOS sandbox profile; the "only allow-listed hosts" rule is a design rule today, not enforced |

## 4. Our own base or dsh

**Our own thin base, as the plan says.** Of dsh's 15 feature groups, our agents need about 6, and the prototype built them in a small amount of code. What our agents need most (company memory with client areas, the way-in check, approvals to people, company-event triggers, replay exams) is not in dsh at all. dsh changes very fast (about 4,300 commits in a month) and brings about 1,700 packages to review. The 6-function contract keeps the door open: dsh can become the core if ours fails, or a worker for coding jobs.

## 5. Not verified

- Real Claude was run once per agent, not at scale; cost and reliability under many runs are not measured.
- No real company system was connected; all data is dummy.
- The learning loop, real connectors and Claude on Vertex are not built.

## v2: what the second build showed

Built Oct 19, 2026, on the same dummy company. v2 adds one company brain, three roles, travel booking, a live call helper and a deal brief. 541 tests pass and all 10 exams pass.

### Exam table: two ways to fill the brain

Three exams read the brain. Each one runs twice. In the first run the brain is filled from the answer keys. In the second run it is filled by the real pipeline: the inbox, then the Cleaner, Extractor, Linker and Playbook writer, over all 31 sources. The pass bars are the same.

| Exam | Seeded from answer key | Through real pipeline |
|---|---|---|
| Project brief (PR05) | PASS: brief cites 6 of 6 key items | PASS: brief cites 6 of 6 key items |
| Deal brief (CareNest, Zaika) | PASS: similar clients right 2 of 2, 0 missed kickoff topics, 0 forbidden cites | PASS: same result |
| Live call helper (LC01, LC02) | PASS: recall 100%, 0 false suggestions per call, contradiction found | PASS: recall 100%, at most 1 false suggestion per call, contradiction found |

The other seven exams do not read a seeded brain. They all pass: finance watch (8 of 8), spend advisor (9 of 9), travel booking (8 of 8 requests right), Cleaner, Extractor (recall 100%, precision 99% on 105 items), Linker (8 of 8 links) and Playbook writer (4 of 4 playbooks, 0 leaks).

### What the honest exam found and fixed

- **The pipeline never wrote a playbook.** The Playbook writer needs a deal id, and the pipeline did not pass one. Now it runs once for each closed deal in the area. After the fix the real pipeline writes 5 playbooks and 12 kickoff checklist questions.
- **One client showed twice in "similar clients".** Client C01 has two won deals. Both playbooks ranked high, so the second similar client was missing. Now each client shows once, with its best playbook.
- **Brain brief sections.** A cited item must now match its section: a decision cannot sit under Blockers. The check refuses a brief that breaks this. The decision "reminders will go by WhatsApp only" is correctly under Recent decisions in the stored data. The blocker line about the WhatsApp approval is a real blocker.
- **A stray comma after "INR" crashed a finance check.** Real Sonnet wrote "INR ," once. The check now ignores it.

### Other changes in this build

- The run loop compacts the conversation before a model call when it nears the window. One test forces a small window and proves it.
- `BrainStore.set_scope` sets an item's project and deal. The Linker's tool uses it, not raw SQL.
- The console starts with the brain filled. "Next day" brings new sources in through the inbox trigger and the pipeline. A failed source is counted and shown, not hidden.
- `run_demo.py` tells the v2 story: new sources arrive and go through the four brain agents, Akbar's project brief, Anthony's deal brief, finance watch, a held travel request, one quiet run, and one refusal.

### Real Sonnet samples

Five samples were recorded with the `claude` CLI and Sonnet, 7 model calls in all (the finance card was tried 3 times). They are in `web_console/real_model_samples.json`.

- Project brief, deal brief, Cleaner and live call summary came back usable. The wording is plain and every point cites its source.
- The finance trip card was stopped twice by our own checks. The first time Sonnet copied a field name with an underscore. The second time it wrote "4450 INR" where the check wants "INR 4,450". The guard worked as designed. The saved sample shows the refused answer.

### Not verified

- Real Claude ran for 5 samples only. Cost and reliability at scale are not measured.
- The real pipeline exam uses the fake model for the four brain agents. Only the samples above used real Claude.
- A browser check of each role (ticket I2) is still to do.
