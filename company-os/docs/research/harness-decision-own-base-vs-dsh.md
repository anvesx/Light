# Domain harness: build our own, or use DeepSeek's dsh?

Companion to `harness-decision.html`. Built by `build.py` from `page.tpl.html` + `diagrams.py`. Same content, ASCII diagrams.

**The direction:** a Company OS (Oct 18 plan), used as a direction, not a build list. Many agents share one company memory; every action goes round record, understand, decide, act, check, remember. Our plugin layer design stays.

**My decisions:**
1. **Base:** our own thin runtime, grown from our loop (v0 to v6). dsh is not the base. If the runtime core (week-1 checks plus "runtime calls only the gateway") is not done by the end of week 3, or 2 of the 4 week-6 runtime tests fail, we switch to dsh behind the same contract (about 3 weeks). Later, dsh can be a worker for coding jobs.
2. **Small shared parts, then one workflow by hand:** company memory v1 (the meeting graph, one area per client) and triggers (timer, a person asking). Generalise after 2 or 3 workflows.
3. **First agent: meeting prep.** Its data, our own meeting record, exists today.
4. **Next:** project risk agent on ClickUp and Slack, or the cost watcher if ClickUp data is missing. Fraud watcher later.
5. **One lifecycle kit;** every agent is a small pack.

```
 ┌───────────────────────────────────────────────────────────┐
 │ 3. Customer layer: config per client                      │
 ├───────────────────────────────────────────────────────────┤
 │ 2. Domain layer: plugins (where the value is)             │
 ├───────────────────────────────────────────────────────────┤
 │ Plugin contract (thin, ours)                              │
 ├───────────────────────────────────────────────────────────┤
 │ 1. Core: our own thin agent runtime, grown from our loop  │
 │    dsh only as a coding worker later, or if a test fails  │
 └───────────────────────────────────────────────────────────┘
```

## The direction: Company OS

The plan's three parts (connect and understand, execute and control, check and improve) are replaced by seven clearer parts. Reasons: some pieces sit in the wrong group (initiative engine, interface builder); memory is the centre, not a list item; "records", "knowledge and search" and "company memory" are one store; approvals, cost limits and client data separation were missing.

```
 ┌──────────────────────────────────────────────────────────┐
 │ Triggers: a timer · an event · a person asks something   │
 └────────────────────────────┬─────────────────────────────┘
 ┌────────────────────────────▼─────────────────────────────┐
 │ Guardrails, on the way in: who asks? may they? budget?   │
 │ (checked before any run starts)                          │
 └────────────────────────────┬─────────────────────────────┘
 ┌────────────────────────────▼─────────────────────────────┐
 │ Agent runtime: runs the agent packs (meeting prep, risk) │
 └────────────────────────────┬─────────────────────────────┘
 ┌────────────────────────────▼─────────────────────────────┐
 │ Guardrails, on every action: permissions, approvals,     │
 │ client data apart, outside text is data not orders, audit│
 └──────┬─────────────────┬──────────────────┬─────────┬────┘
 ┌──────▼─────┐ ┌─────────▼──────┐ ┌─────────▼──────┐ ┌▼───────────┐
 │ Connectors │ │ People surface │ │ Company memory │ │ Evaluation │
 └────────────┘ └────────────────┘ └────────────────┘ └────────────┘
```

A person's question is a trigger too: it passes the way-in check before any run starts, and every action during the run is checked again.

```
 Record ─► Understand ─► Decide ─► Act ─► Check ─► Remember ─┐
   ▲                                                         │
   └─────────────────────────── loop ────────────────────────┘
```

| Part | Job | Lifecycle step | Our piece |
|---|---|---|---|
| Triggers | Start work: timer, event, request | Record | Initiative engine |
| Connectors | Read and write company tools | Record, act | Fathom, Slack, ClickUp adapters |
| Company memory | Decisions, workflows, results | Understand, remember | Meeting graph is v0 (71 items) |
| Agent runtime | Run each workflow | Understand, decide | Our own runtime, lifecycle kit, packs, AI gateway |
| Guardrails | Way in: who asks, may they, budget. Every action: permissions, approvals, client data apart, audit | Before record; decide, act | Way-in check, read-only gate, run log, cost plugin |
| Evaluation | Score agents | Check | Replay exams, planted cases, cost per case |
| People surface | Where people meet agents | Act | Slack now, screens later |

**Where we differ from the plan:** one workflow by hand first, generalise after 2 or 3 (not general agents first); the real market gap is a shared company memory (event-started agents such as AWS FinOps Agent already exist); one plain fixed surface (Slack) first, screens on the fly later; seven parts, not three.

**DevX problems to agents:** late requirements → meeting prep; drift from SOW, overload, client silence, missed commitments → risk agent; SOW estimates → estimation loop inside it; full KT → team knowledge agent; travel at about 25% of salary → finance agent; hiring → hiring agent; uneven quality → standards agents.

## What we built
- Our own loop in 7 steps (`../ladder-code/v0` to `v6`): loop, tools + sandbox, context caps + compaction, memory, verdict checks, workflows where the harness builds the SQL, append-only log. v0, v1, v2, v5, v6 tested with a fake model on Oct 13 to 14; v3, v4 syntax only. The test files were lost, so they must be written again (week 1).
- Fraud watcher design: simulator → scan (code) → investigate (model) → check (code) → case board → memory; score against planted cases.
- Data research (structure and counts only): cash refunds, cancel to gift voucher and remakes are strong signals; staff-level refunds and discounts need POS data.

## What we learned
- **Treat a prompt cache miss like a bug:** fixed start, no clock in the prompt, sorted tools, never add or remove tools per turn, append notes, hash each part, summarize while warm.
- Loop: cap tool output, compact below the window, harness builds dangerous actions, deny before run, verdict step, append-only log.
- Domain: model only for judgement, data decides what the agent can see, never say "fraud", dummy data first.

## Own harness vs dsh

### For a Company OS: what dsh offers, against what we need (12 weeks)

| dsh feature | Need it? | What we have or do instead |
|---|---|---|
| Agent loop: steps, turns, cancel | yes | Our loop v0, already written |
| Retries and error recovery | yes | Small to add; counted in the "missing parts" test |
| Cache-safe prompt order | yes | Our cache rules; gateway counts cache hits |
| Tool pipeline: policy, approval, guard | yes | Our tool gate (v1) plus guardrails; approvals go to a person in Slack |
| Session log, resume | yes | Our append-only run log (v6), already written |
| Output caps | yes | Our 8,000-character cap (v2), already written |
| Compaction at 80% | rarely | Short runs; load only needed memory items; our `compact()` untested |
| Model adapters for many providers | one route | Runtime calls our gateway; the gateway picks the model |
| Token meter | elsewhere | The gateway logs tokens and cost |
| OS sandbox for shell commands | no | No shell commands in first agents; container with no secrets |
| MCP client | later | Our own connectors; add an MCP library when needed |
| Scheduled reminders | no | Needs a running dsh app; our triggers instead |
| Subagents, agent teams, skills | no | Not in first agents |
| Web, desktop, terminal UI, LSP, browser and computer control | no | People see the work in Slack |
| SDKs, plugin manager, profiles, hot reload | no | Our 6-function contract |

Not in dsh at all, and built on either core: shared company memory with client areas; the way-in check; approvals and flags to a person in Slack; triggers from company events; replay exams and cost per run. Where dsh is clearly better: compaction, deep error recovery, MCP, long coding tasks; so dsh stays as a coding worker for later, and the week-6 "missing parts" test switches us if we need too much of it.

**Current answer: our own thin runtime, not dsh** (Company OS scores: dsh behind contract 25, own runtime 33).

### Earlier: the first comparison, for one agent (its pick, E, is replaced)
| Option | Score of 40 |
|---|---|
| A. dsh directly | 25 |
| B. Fork dsh | 25 |
| C. From scratch | 30 |
| D. Own core on a library | 31 |
| F. Own thin runtime (new pick, scored in decision 1) | n/a |
| E. dsh behind our contract | 33 to 34 (earlier pick, replaced) |

dsh has: cache-friendly prompt order, compaction at 80% that reuses the prefix, a tool safety pipeline, an append-only session log, a token meter, schedule/jobs, no privileged core. Vertex: Gemini built in; Claude through a small gateway on a custom `anthropic-messages` route (`provider.ts:47`; read from source, not run; dsh pins pi-ai 1.1.0 with a patch, we read 1.3.0).

## Our runtime and the contract

**Who owns what:** triggers, lifecycle kit and packs, company memory (one area per client), the contract, our runtime (loop, tool gate, run log; the guardrails run through the contract, so they work on either core) and the AI gateway (only exit for model calls; connectors reach only allow-listed company APIs) are all ours. dsh is not in the main path; later it may run one coding job in a sandbox.

**The contract (ours, always):** `runTask`, `addTool`, `beforeRequest`, `beforeTool`, `afterTool`, `afterReply`. Plugins import only this. It runs on our runtime; on dsh it would map to headless `--json`, the tool registry, `agent/request`, `tools/pre-execute`, `tools/post-execute` and session events.

**dsh changes fast:** about 4,300 commits from Sep 16 to Oct 15, 2026; 14 stored-data format changes after the first version on Sep 11; session format at v4. Measures 1 to 4 hold always, by design (they keep us free to switch). Contract tests (11) are written in week 1 and run on dsh only if we switch. The rest apply only if we run dsh (as a coding worker, or after a switch).

| # | Tie to dsh | Measure |
|---|---|---|
| 1 | Plugins call dsh | Import only our contract |
| 2 | History in dsh format | Our own run log via afterTool/afterReply |
| 3 | Memory, cases in dsh | Company memory |
| 4 | dsh `schedule` needs a running Host | Our triggers call `runTask` |
| 5 | Settings in dsh profiles | One config of ours; adapter writes the patch file |
| 6 | Model routing in dsh | dsh sees one route: our gateway |
| 7 | Update breaks the cache | Gateway counts cache hits, alerts on a drop |
| 8 | Session log sent to DeepSeek | Turn off `session-log-deepseek`; network only to gateway |
| 9 | Sandbox limits writes only | Our guardrails in `beforeTool`; container with no prod secrets |
| 10 | Auto updates | Pin version and lockfile; keep a copy |
| 11 | Swap is only a claim | Same contract tests on dsh and our runtime before switching |
| 12 | dsh-only features creep in | Use only loop, tool pipeline, compaction |

Upgrade gate (if we run dsh): new version → contract tests → replay exam (same score, cost per case) → pin, else stay.

## My decisions

**1. Base: our own thin runtime; dsh as a coding worker later.** For one agent, dsh behind a contract won. For a Company OS it does not: our agents are short, event-started workflow runs (dsh is built for long coding sessions by one person); our loop v0 to v6 already covers what they need; the 12 measures cost about as much as building our own; clients will review code that touches their data (dsh: about 1,700 packages in its lockfile; no public audit; built by DeepSeek; client objection is our judgement); our runtime is built for many users and client areas, while dsh's session model is built for one user; the guardrails run through the contract on either core.

| Test | dsh behind contract | Own runtime | Own runtime + dsh coding worker |
|---|---|---|---|
| Total of 40 (my estimates) | 25 | 33 | 34 |

If we switch at week 3: weeks 4 to 6 build the dsh adapter and measures and pass the guardrail gate on dsh; meeting prep moves to weeks 7 to 9, the second agent to weeks 10 to 12. Why not start on dsh and decide later: making dsh safe is about as much work as runtime v1, and would be thrown away if we then moved. The week-3 exit limits the risk instead. Needs the team's agreement, because it changes "starting on dsh is fine".

**2. Small shared parts, then one workflow by hand.** Company memory v1 extends the meeting graph (71 items, links such as "supersedes" and "refines") with one area per client and every agent run; ClickUp comes later with the second agent. Triggers v1: a timer and a person asking in Slack (week 2), calendar events if allowed (week 3). Every trigger passes the way-in check.

**3. First agent: meeting prep.** Scores (of 40, my estimates):

| Meeting prep | Project risk | Cost watcher | Fraud watcher | Finance |
|---|---|---|---|---|
| **31** | 30 | 28 | 25 | 24 |

Lifecycle: record (meetings into memory; a run starts on a calendar event or a request) → understand (code: open questions, decisions, tasks, changed decisions for this project) → decide (model: what to settle; each question cites a memory item) → act (private Slack brief to the attendee; never the client) → check (code: every question cites a real item; no other client's items) → remember (after the meeting, mark which questions were answered). Score: replay past meetings with only earlier memory; count decisions in meeting N the brief asked about; plus a lead's rating. Not checked: calendar access (fallback: a person asks); client records start with research meetings and one client with the lead's agreement.

**4. Next:** risk agent (ClickUp checked in week 5), or the cost watcher if ClickUp data is missing. Cost plugin stays in the base. Fraud, finance, hiring, knowledge and standards agents later. After 2 or 3 agents, move the shared shape into the kit.

**5. One base, one lifecycle kit, many agent packs:**
```
 ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
 │ Meeting  │ │ Risk     │ │ Finance  │ │ Cost     │ │ Fraud    │
 │ prep 1st │ │ 2nd      │ │ (later)  │ │ (later)  │ │ (later)  │
 └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
 ┌────▼────────────▼────────────▼────────────▼────────────▼─────┐
 │ Lifecycle kit: record · understand · decide · act · check ·  │
 │ remember (built once)                                        │
 └──────────────────────────────┬───────────────────────────────┘
 ┌──────────────────────────────▼───────────────────────────────┐
 │ Base: company memory · triggers · the contract ·             │
 │ AI gateway · cost plugin · guardrails (way in + every action)│
 └──────────────────────────────┬───────────────────────────────┘
 ┌──────────────────────────────▼───────────────────────────────┐
 │ Our agent runtime (grown from our loop); coding worker later │
 └──────────────────────────────────────────────────────────────┘
```
Cost plugin is not the cost watcher: the plugin (base) logs cost on every call for every agent; the watcher is a later pack.

**Dummy to real:** dummy data → shadow (real data, hidden) → live read-only (a person decides) → live actions (approved). Only the data source and config change.

**How it can break:** briefs hard to score (replay exam plus a lead's rating); garbled transcripts (gap-fill; questions cite sources); client meeting records are client data (one area per client; research meetings and one client first); no calendar access (a person asks); our runtime late or unreliable (exit at week 3 or week 6).

## Plan

```
 ┌──────────────┐  ┌──────────────────┐  ┌──────────────┐  ┌──────────────┐
 │ Weeks 1-2    │─►│ Weeks 3-6        │─►│ Week 6       │─►│ Weeks 7-12   │
 │ runtime v1,  │  │ meeting prep,    │  │ keep or      │  │ risk agent   │
 │ gateway,     │  │ replay exam,     │  │ switch?      │  │ or cost      │
 │ way-in check,│  │ shadow run;      │  │ 4 tests +    │  │ watcher; the │
 │ memory v1    │  │ exit if late     │  │ guard gate   │  │ shared shape │
 └──────────────┘  └──────────────────┘  └──────────────┘  └──────────────┘
```

| Week | Step | Done when |
|---|---|---|
| 1 | Rewrite the lost loop tests; runtime v1 core: loop, tool gate, run log; direct model calls | New v0 to v6 tests pass, fake model and real API |
| 1 | Plugin contract and contract tests on our runtime | Contract tests pass; every call in our run log |
| 2 | Gateway to Claude on Vertex; runtime calls only the gateway | Cost, cache and usage numbers for every call; a direct model call is blocked |
| 2 | Way-in check before every `runTask` | Unknown caller and over-budget run refused and logged |
| 2 | Company memory v1: meeting graph (add Oct 8 to 13), one area per client, runs | A read across client areas is refused |
| 2 | Triggers v1: timer and a person asking in Slack | Both start a run through the way-in check |
| 3 | Lifecycle kit; every-action checks (permissions, approvals, outside text is data not orders, audit) | One full run on a past meeting; all actions audited; a forbidden tool call blocked; a risky action waits for approval; a planted order in a transcript ignored and logged |
| 3 | Connectors: Fathom, Slack (read), calendar if allowed | A new meeting reaches memory without help, in the right client area or a hold area |
| 4 | Meeting prep pack and replay exam | On every replayed meeting with decisions (at least 3), half of them were asked about |
| 5 | Shadow run to me only; check ClickUp data for 3 projects | A lead rates a week of briefs; ClickUp gap written down |
| 6 | Runtime tests (reliability, cost control, missing parts under 3 days, upkeep) and the guardrail gate | Keep our runtime or switch; guardrail gate passed on either core |
| 7-12 | Risk agent or cost watcher; then the shared shape | Same replay exam and shadow run |

2 of the 4 runtime tests fail: switch to dsh behind the same contract (weeks 7 to 9: adapter, the 12 measures); the second agent starts in week 10. The guardrail gate (six cases: unknown caller, over budget, other client's area, forbidden tool call refused; risky action held for approval; orders in client text ignored) must pass on either core before going live. A week-3 switch (runtime core not done) moves meeting prep to weeks 7 to 9; a week-6 switch re-runs the replay exam and the gate on dsh.
