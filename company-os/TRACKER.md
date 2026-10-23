# Tracker

What is done, what is in progress, what is next, and the decisions made. Update this file with every change. Newest first in each section. Times are IST.

Last updated: Oct 22, 2026.

## In progress

| What | Ticket | Notes |
|---|---|---|

## Next

| What | Ticket | Notes |
|---|---|---|
| 24/7 step 1: check the stop switch before every action, add a pause for each agent, and cheap-first models (Haiku first, Sonnet when needed, never Opus) | (planned) | See `PLAN_24x7.md`, ideas 1 and 2 |
| 24/7 step 2: crash resume (save after each step), one effect per repeated write, and a watchdog that alerts a person | (planned) | See `PLAN_24x7.md`, idea 3. Part of the control plane server below |
| 24/7 step 3: release gate (exams pass 3 times in a row, then a shadow run), planted-problem test and planted-secret test | (planned) | See `PLAN_24x7.md`, idea 7 and section 5 |
| 24/7 step 4: mark every action undoable or not, and autonomy levels (Shadow, Suggest, Act) | (planned) | See `PLAN_24x7.md`, ideas 5 and 6 |
| 24/7 step 5: every correction or failed run becomes a rule and an exam case | (planned) | See `PLAN_24x7.md`, idea 8. Comes before the learning loop |
| One cloud VM per user: VM provider interface, VM daemon, one box per agent (Linux user, Chrome profile, allowlist), live-view sign-in, snapshots, pause and wake | (planned) | See `docs/research/per-user-vms.md`. Needs the password broker and the stop switch first |
| Check the console at phone width (390 px) and in dark mode | (follow-up) | Not checked in I2 |
| Finance trip card: the real-Sonnet sample was refused twice by our own checks; fix the prompt so it passes | (follow-up) | Found in I1 |
| Control plane server, to run for real: a scheduler for timers, a webhook for new Fathom recordings, a job queue with retries, approvals and letters through Slack or email, hosting | (planned) | After the demo. Today the control-plane logic runs on a simulated clock with dummy data |
| Approvals that expire after a set time (idea from Grok Bot) | (planned) | Now part of `PLAN_24x7.md`, idea 6 |
| Brain inbox reads any document type: Excel and CSV, PDF (with OCR for scans), PowerPoint, Google exports, images. Each fact still links to its exact place (sheet and cell, page and line, slide) | (planned) | Owner's plan, Oct 19. Today: Fathom, Word, email, chat, live calls |

## Done

| Date | What | Ticket |
|---|---|---|
| Oct 22 | Research and design: one cloud VM per user, agent boxes inside it, sign-in through a live view, hosting options and cost | `docs/research/per-user-vms.md`, `README.md` |
| Oct 21 | Plan for running agents 24/7: eight control-plane ideas, autonomy levels, rules that never change, and a build order | `PLAN_24x7.md` |
| Oct 19 | Browser-check fixes: a CSM no longer sees deal-stage sources (sales calls before the signed SOW), enforced on the data; only real changed decisions show "Changed on"; Home cost total matches the runs. 551 tests, 10 exams pass | (fix) |
| Oct 19 | Browser check of each role: all pages work for Ammar, Akbar and Anthony; forbidden pages refused (403); 4 bugs fixed; screenshots in `evaluation/browser_check/` | I2 |
| Oct 19 | Code split into `core/` (core harness) and `control_plane/`, with `contract/` between them. Boundary tests check both directions. 545 tests and all 10 exams pass | R2 |
| Oct 19 | Integration: compaction runs before each model call; exams also run on a brain filled by the real pipeline, and all pass; 3 bugs fixed; real-Sonnet samples recorded (4 of 5 usable) | I1 |
| Oct 19 | Research: Grok Bot inside vs Company OS. Direction sound; ideas to copy: approvals that expire, teach mode, limits on routines (`docs/research/grok-bot-internals-vs-company-os.md`) | (research) |
| Oct 19 | Wave 2: Cleaner, Extractor, Linker and Playbook writer (the brain's four agents); CSM project brief; Growth deal brief; live call helper; finance v2 with real cheaper flights and hotels and round-trip booking; console shell with three people. 526 tests pass; all 10 exams pass | S1 to S7 |
| Oct 19 | Wave 1 integration: full suite green (410 tests); exams pass for meeting prep, finance watch, spend advice and travel booking; names changed to Ammar, Akbar and Anthony; job title "R&D lead" renamed to CTO | (lead) |
| Oct 19 | Repo created at `anvesx/company-os` (private) | |
| Oct 19 | Compaction in `runtime/compaction.py`, adapted from dsh commit `687f282` (MIT) | R1 |
| Oct 19 | Travel booking agent: best 3 options by policy; booking waits for Admin approval. Exam 8 of 8 | F4 |
| Oct 19 | Brain store: inbox, readers, router, search, unconfirmed items, meeting filter | F2 |
| Oct 19 | Three roles enforced on the data: Admin, CSM, Growth | F3 |
| Oct 19 | Dummy data v2: 31 sources (Fathom, Word, email, chat) in Hindi, English and Hinglish; 4 past and 2 live deals; 105 answer-key items | F1 |
| Oct 19 | Only the finance and meeting prep agents stay. The other five agents moved to `experiments/` | X0 |
| Oct 19 | Plan and tickets for v2 | `PLAN_v2.md`, `TICKETS_v2.md` |
| Oct 18 | v1 prototype: 8 agents, guardrails, company memory, web console, exams | `RESULTS.md` |

## Decisions

| Date | Decision | Why |
|---|---|---|
| Oct 22 | Each user gets one cloud VM. All of that user's agents work inside it, each as its own Linux user with its own browser profile and allowlist. Finance gets its own VM. Company agents run in a company service VM | The user signs in once and every agent can work, without using the user's Mac. Boxes keep agents apart at a fraction of the cost of one VM per agent |
| Oct 22 | The agent never sees a password: a broker fills logins from 1Password after the user approves each fill | A leaked password in a browser snapshot is a known failure in a similar product |
| Oct 21 | Running agents 24/7 is a control-plane job. The core harness does not change | The core and the brain work. What unattended runs lack is cost control, a stop switch, crash resume, an always-on server and release gates |
| Oct 21 | Autonomy is earned: every new agent starts in shadow, moves up only on measured results, and drops a level by itself after a serious mistake. Actions that cannot be undone always wait for a named person | Trust should follow results. Undo is a safer test than which agent acts |
| Oct 21 | An agent can never change its own exams, budget, level or stop switch | An agent that grades itself cannot be trusted |
| Oct 19 | Split the code into `core/` (core harness) and `control_plane/`, with `contract/` between them and a test that the core never imports the control plane | Makes the two layers visible and keeps the core swappable (for dsh or another harness) |
| Oct 19 | Explain Company OS as two layers: the core harness (how one agent thinks and acts during a run) and the control plane (how the company runs many agents safely, always on) | The core harness is small; most of the value is in the control plane |
| Oct 19 | All research goes in the repo, in `docs/research/` | One place for the team to read why decisions were made |
| Oct 19 | Keep Python for the core (brain, agents, guardrails, document readers). If we need dsh features later, run dsh as a separate TypeScript service behind our contract. | Python was inherited from the first prototype, not chosen on purpose; checked Oct 19. Python needs no packages and is strong for documents (Excel, PDF, OCR). dsh is TypeScript, so we rewrite its ideas in Python. Revisit if the maintaining team mostly writes TypeScript |
| Oct 19 | The web console is only for experiments: to see progress visually and try things out. It is not the final product. | How people will reach the agents (Slack, email or another tool) is still open |
| Oct 19 | Count compaction as one of the 7 dsh features our base has, like the other six | Code we take from dsh is our own code too: use dsh directly, or write our own |
| Oct 19 | Every Fathom recording goes into the brain automatically. Nobody approves anything. Unsure facts are stored as "unconfirmed". When two statements conflict, the newer one wins and the older one is marked "superseded". | A required review step would be a hassle, and people would stop doing it |
| Oct 19 | Only these recordings go in automatically: a meeting with at least one attendee from outside DevX, or a meeting whose title matches a known client. An internal meeting goes in only if `#brain` is in its title. | Keeps one-on-ones and HR talks out of company memory. Default; the owner may change it |
| Oct 19 | Three roles: Admin (Ammar Khan), CSM (Akbar Ali), Growth (Anthony Fernandes). The console shows one person per role. | Show each view from one person's point of view |
| Oct 19 | Growth reads lessons from past clients with names removed, never another client's raw transcripts | Keeps client data separate |
| Oct 19 | Meeting prep and finance are each a family of three small agents | Each agent gets only its own tools. For example, travel booking cannot read the books |
| Oct 19 | Keep our own base. It has the 7 dsh features we need, compaction included. For more later (browser control, subagents, skills, a web app), use dsh directly or write our own code. | Code is a commodity. The value is our memory, guardrails and data. dsh is MIT licensed |
| Oct 19 | Keep only the finance agent (with travel booking) and the meeting prep agent | Focus. Finance watch was the first pick of 56% in the simulated focus group |
| Oct 19 | The finance agent shows the actual cheaper flights and hotels (airline, flight number, time, fare; hotel name, rate) | "A cheaper option existed" is not useful on its own |
| Oct 18 | Our own thin runtime, not dsh, as the base | Our agents need 7 of dsh's 25 features. What they need most is not in dsh |
| Oct 18 | The learning loop is designed but not built yet | Owner's call |

## Open questions

| Question | Owner |
|---|---|
| Which host runs the user VMs: E2B, Daytona or EC2 in Mumbai? Must client data stay in India? Suggestion: E2B or Daytona to start; EC2 in Mumbai if data must stay in India | Pratham |
| Which actions count as undoable? Suggestion: create a task, send an internal reminder | Pratham |
| What result lets an agent move up a level? Suggestion: no worse than a trained person, over at least 50 reviewed runs | Pratham |
| Which language does the team that will maintain Company OS mostly write? If TypeScript, revisit the Python decision | Pratham |
| How will people reach the agents in the final product (Slack, email or another tool)? The web console is only an experiment | Pratham |
| Confirm the rule for which recordings go into the brain | Pratham |
| Check how Fathom webhooks work before connecting real data (polling every 10 minutes is the fallback) | Lead |
| Which travel API to use for real fares and bookings | Pratham |
| Add meaning-based search (embeddings) next to topic keywords when real data arrives | Lead |
