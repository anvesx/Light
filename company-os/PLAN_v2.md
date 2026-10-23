# Company OS v2: plan

Owner: Pratham Bhatia. Team lead: Rachit Srivastava. Written Oct 19, 2026. Build tickets: `TICKETS_v2.md`.

## 1. Goal

Company OS v2 has **two agents** and **one company brain**.

1. **Finance agent.** It finds money that needs a look (finance watch), shows real cheaper flights and hotels for each past trip (spend advice), and books new trips (travel booking). A booking waits for an Admin's approval.
2. **Meeting prep agent.** It prepares a CSM for a project call, prepares Growth for a deal call and the kickoff, and listens to a live call to suggest the next question.
3. **Company brain.** All company knowledge goes into one central memory: decisions, requirements, blockers, client discussions, deals, revenue, what helped and what did not. Input comes from any source: Fathom transcripts (Hindi, English or Hinglish), Word documents, emails, chats and live calls. Four internal agents clean, extract, link and summarise it. Every stored fact links back to the exact source lines.
4. **Three roles:** Admin, CSM and Growth. Each role sees only its own data. The rule sits in the guardrails and the memory scopes, not only in the UI.

All other v1 agents move to `experiments/`. The shared core stays. Everything still runs on dummy data with a deterministic fake model. Real Claude (Sonnet, never Opus) is opt-in.

## 2. What we changed from the brief, and why

| Brief | v2 decision | Reason |
|---|---|---|
| Meeting prep is one pack with three modes | One **family** of three small packs (`project_brief`, `deal_brief`, `live_copilot`) in one folder, shown to people as one agent | Each pack gets only its own tools. The project brief cannot read the playbook library; the deal brief cannot read project delivery data. Each mode keeps its own exam |
| Finance agent is one pack | One family of three packs (`finance_watch`, `spend_advisor`, `travel_booking`), shown as one agent | Same reason: travel booking must never read the books. The two existing exams stay unchanged |
| Live copilot calls the model on every line | One guarded run per call. Code checks each line against the checklist and past decisions (under 200 ms). The model writes only the end summary and optional wording | A model call per line costs too much and is too slow for "within seconds". Code checks are exact and testable |
| Growth sees no travel | Every role may **request its own trip**. Only Admin sees company travel spend and other people's trips | Booking is self-service. Spend data is still Admin only |
| Growth reads past clients' data | Growth never reads another client's raw items. It reads a **library area** of redacted playbooks, written only by the Playbook writer | Keeps the client areas closed. Only the lessons cross, never the transcripts |
| Move POS and project-risk dummy data | The core generator keeps making that data | It shares one random stream with the data our two agents use. Moving it would change every planted case and answer key |

## 3. Architecture

```
  SOURCES (any kind)                     COMPANY BRAIN (control_plane/company_brain/)
  Fathom JSON (hi/en/Hinglish) ──┐       ┌──────────────────────────────────────────────────┐
  Word .docx ────────────────────┤       │ inbox: read file → split lines → route to area   │
  Email .eml ────────────────────┼─────► │   (attendee email → client; unknown → hold area) │
  Chat export .txt ──────────────┤       │                                                  │
  Live call lines ───────────────┘       │ internal agents (normal guarded runs, "system"): │
                                         │  Cleaner → Extractor → Linker → Playbook writer  │
                                         │  low confidence → review queue → a person        │
                                         └───────────────────────┬──────────────────────────┘
                                                                 │ writes
                                                                 ▼
  ┌──────────────────────────── COMPANY MEMORY (one SQLite file) ─────────────────────────────┐
  │ client areas C01..C10 (one per client or prospect)   library area "playbooks" (redacted)  │
  │ devx-internal (finance)    hold (not yet routed)      runs, steps (append-only), scores   │
  └──────────────▲──────────────────────────▲──────────────────────────▲──────────────────────┘
                 │ scoped reads             │ scoped reads             │ scoped reads
  ┌──────────────┴───────────┐  ┌───────────┴─────────────┐  ┌─────────┴─────────────────────┐
  │ MEETING PREP AGENT       │  │ FINANCE AGENT           │  │ WEB CONSOLE (web_console/)    │
  │ project_brief  (CSM)     │  │ finance_watch           │  │ role switcher: 3 people       │
  │ deal_brief     (Growth)  │  │ spend_advisor + trips   │  │ pages discovered as plug-ins  │
  │ live_copilot   (both)    │  │ travel_booking ──► held │  │ every API call checks role    │
  └──────────────┬───────────┘  └───────────┬─────────────┘  └───────────────────────────────┘
                 │                          │
  ┌──────────────┴──────────────────────────┴───────────────────────────────────────────────┐
  │ SHARED CORE (unchanged in shape): triggers → way-in check → lifecycle kit (record,      │
  │ understand, decide, check, act, remember) → runtime loop → every-action check → gateway │
  │ (fake model default; claude-cli = Sonnet) → people surface (letters, approvals)         │
  │ NEW in guardrails: role_scopes.py (Admin, CSM, Growth; areas and data kinds per role)   │
  └─────────────────────────────────────────────────────────────────────────────────────────┘
```

Rules that do not change: code finds, the model explains. Check comes before act. Outside text is data, never orders. Quiet runs make no model call. Every read and action is in the append-only run log.

## 4. Brain schema

The brain tables live in the company memory database (`company_memory.db`), so there is one memory. `control_plane/company_brain/schema.sql` adds them. Existing tables stay.

| Table | Key columns | What it holds |
|---|---|---|
| `areas` (existing) | `kind` adds `library` | One area per client or prospect, plus `devx-internal`, `hold`, and the library area `playbooks` |
| `sources` | `source_id, area_id, kind, title, origin_ref, occurred_at, received_at, language, participants, project_id, deal_id, status, raw_text` | One input. `kind`: fathom, docx, email, chat, live_call, paste, record. `language`: en, hi, hinglish, mixed. `status`: received, cleaned, extracted, linked, needs_review, failed |
| `source_lines` | `source_id, line_no, speaker, speaker_id, t_sec, raw_text, clean_text, lang` | Each spoken line or paragraph. The raw text is never changed. The clean English text sits next to it |
| `items` (existing) | `kind` adds requirement, blocker, commitment, risk, money, sentiment | One fact. `topic` comes from the topic lexicon |
| `item_facts` | `item_id, project_id, deal_id, confidence, speaker_id, said_at, state, value` | Brain detail per item. `state`: active, superseded, resolved, dropped. `value`: a date, amount or choice as JSON |
| `evidence` | `item_id, source_id, line_from, line_to, quote_raw, quote_clean` | The source span. Every brain item has at least one row |
| `links` (existing) | `rel` adds `contradicts`, `same_as` | supersedes, answers, refines, follows_up, about, contradicts, same_as |
| `projects` | `project_id, area_id, name, status, csm_id, lead_id, start_on, planned_end_on, sow_value_inr` | Copied from company records |
| `deals` | `deal_id, area_id, title, stage, owner_id, industry, value_inr, opened_on, closed_on, outcome_note, tags, project_id` | `stage`: discovery, proposal, closing, won, lost. `deal_id` = the CRM lead id |
| `revenue` | `area_id, project_id, month, amount_inr` | Revenue per client per month |
| `review_queue` | `review_id, area_id, source_id, proposed, reason, confidence, status, decided_by, decided_at, item_id` | Items under 0.6 confidence and lines the Cleaner could not translate. A person accepts or rejects |
| `playbooks` | `playbook_id, source_area_id, deal_id, client_label, industry, outcome, revenue_inr, sections, tags, updated_at, run_id` | Area `playbooks`. `sections`: initially_wanted, later_changed_to, chose, went_right, went_wrong. Each entry: text, topic, item ids |
| `kickoff_checklist` | `check_id, topic, question, why, learned_from, industries` | Area `playbooks`. Questions to ask at kickoff, learned from requirements that came late in past projects |

## 5. RBAC: three roles

A role comes from the person's job in the people table: `ceo`, `rnd_lead`, `finance_lead` → **Admin**; `csm` → **CSM**; `growth` → **Growth**. Other jobs get no console. `control_plane/guardrails/role_scopes.py` holds the whole matrix. The way-in check, the memory scopes and every console API call use it.

**Areas each role can read**

| Area | Admin | CSM | Growth |
|---|---|---|---|
| Client areas of own projects (CSM on the client or project) | yes | yes | no |
| Prospect and lost-deal areas the person owns | yes | no | yes |
| Other clients' areas | yes | no | no |
| Library `playbooks` (redacted playbooks, kickoff checklist) | yes | no | yes |
| `devx-internal` through finance tools | yes | no | no |
| `devx-internal` through travel booking tools (own requests only) | yes | yes | yes |
| `hold` (sources not yet routed) | yes | no | no |

**Pages each role can open**

| Page | Admin | CSM | Growth | What it shows |
|---|---|---|---|---|
| Home | yes | yes | yes | Cards from the pages this role may open |
| Brain inbox | all areas | own areas | own areas | Drop a file or paste a transcript, watch the four internal agents, see items with source links |
| Review | all areas | own areas | own areas | Low-confidence items and untranslated lines to accept or reject |
| Meeting prep | yes | own projects | no | Project brief before a client call |
| Deals and playbooks | yes | no | own deals + library | Deal brief, closing ideas, kickoff checklist, past playbooks |
| Live call | yes | own project calls | own deal calls | A simulated two-person call with suggestions as it plays |
| Finance | yes | no | no | Finance watch findings, trip cards with real cheaper options, spend split |
| Travel | all requests | own requests | own requests | Ask for flights for N people, best 3, booking waits for Admin |
| Approvals | approves bookings and follow-ups | own follow-ups | none | Held actions |
| Runs and cost | yes | no | no | Every run step by step, guardrail verdicts, cost, cache hits |

**Data each role can see**

| Data | Admin | CSM | Growth |
|---|---|---|---|
| Requirements, decisions, blockers, questions of a project | all | own projects | no |
| Deal discussions and stage | all | no | own deals |
| Past-client playbooks | yes | no | yes |
| Revenue per client | yes | no | only inside playbooks and own deal value |
| Books, invoices, budgets, trip verdicts, team travel spend | yes | no | no |
| Salaries | team totals only | no | no |
| Own trip requests and bookings | yes | yes | yes |

**Privacy rules from the focus group** (market simulation, Oct 18): the finance agent stays read-only except a booking that a person approves. Every finding links to its source record (invoice, trip, transcript line). Trip cards show the team and trip id, not the traveller's name. The brain stores no opinion about a DevX person's performance, and nothing is scored per person. No data is used for appraisals; the console says so on the Home page.

## 6. One person per role

The console role switcher shows exactly three people.

**Admin: Ammar Khan (CEO).**
1. Home shows: 6 new sources in the brain today, 2 waiting in the hold area, 3 finance findings, 1 booking waiting for approval.
2. He opens Finance. Trip `TR0xx` says: paid Sarang Airways `SRG 214` at 14:45 for INR 12,400, booked 1 day before. Cheaper: Tarang Air `TRG 118` at 14:00 for INR 6,640, seen 10 days before. Hotel: paid Harbour Crest at INR 9,200; Marine Lane Inn was INR 7,100.
3. He approves Akbar's booking for 2 people. The simulated booking reference appears.
4. He routes an email from the hold area to the right client, and the brain processes it.
5. Runs and cost shows each run's six steps and guardrail verdicts.

**CSM: Akbar Ali (MedBridge, Tailorbird, Nimbus).**
1. Home shows: MedBridge sync tomorrow 11:00 AM IST, 3 open requirements, 1 blocker open for 9 days.
2. "Prep me" gives questions to ask, open requirements, blockers and one changed decision. Each line links to the Fathom line (Hinglish original next to the English).
3. She drops a Hinglish transcript into the Brain inbox and watches Cleaner, Extractor and Linker work.
4. In Live call, the copilot says: "The client now says SMS. On Sep 30 you decided WhatsApp (source line 14). Ask if the decision changes."
5. She asks Travel for 2 people Mumbai to Pune on Oct 28, sees the best 3, and the booking waits for Admin.
6. She cannot open Deals, Finance or Kabir's clients.

**Growth: Anthony Fernandes (CareNest and Zaika deals).**
1. Home shows: CareNest Clinics (closing) and Zaika Foods (proposal).
2. The CareNest deal brief finds similar past deals: a clinic chain booking app (won) and a diagnostics lab (lost: the data storage question was never answered).
3. Closing ideas cite what helped before, such as a paid pilot for one clinic.
4. The kickoff checklist asks, on day one, what past clients asked for late: insurance claim upload, WhatsApp or SMS reminders, Hindi screens, where data is stored.
5. In Live call with CareNest, suggestions appear as the call plays.
6. He cannot open Finance, salaries, project briefs or any past client's raw transcripts.

## 7. What moves to `experiments/`

`experiments/README.md` says how to restore each part. Nothing in the core imports `experiments/`, and the test run does not include it.

| From | To |
|---|---|
| `agents/project_risk/`, `agents/fraud_watch/`, `agents/hiring_forecast/`, `agents/delivery_progress/`, `agents/client_requests/` | `experiments/agents/<same name>/` |
| `control_plane/connectors/project_tools.py`, `project_hours.py`, `store_pos_tools.py`, `staffing_tools.py`, `git_tools.py`, `progress_views.py`, `client_request_tools.py` | `experiments/connectors/` |
| `company_data/generate_git_activity.py`, `company_data/generate_client_requests.py` (their flags in `build()` now default to off) | `experiments/company_data/` |
| `web_console/progress_page.py`, `web_console/client_requests_page.py`, copies of v1 `department_scenarios.py`, `agent_cards.py`, `static/console.js` | `experiments/web_console_v1/` |
| `tests/test_agent_project_risk.py`, `test_agent_fraud_watch.py`, `test_agent_hiring_forecast.py`, `test_agent_delivery_progress.py`, `test_agent_client_requests.py`, `test_client_request_tools.py`, `test_client_requests_data.py`, `test_git_activity_data.py`, `test_git_tools.py`, `test_progress_views.py`, and the cut-out parts of `test_connectors.py`, `test_company_data.py`, `test_web_console.py` | `experiments/tests/` |

Kept agents are regrouped (agent names do not change):

| From | To |
|---|---|
| `agents/finance_watch/` | `agents/finance/watch/` |
| `agents/spend_advisor/` | `agents/finance/spend_advice/` |
| (new) | `agents/finance/travel_booking/` |
| `agents/meeting_prep/` | `agents/meeting_prep/project_brief/` |
| (new) | `agents/meeting_prep/deal_brief/`, `agents/meeting_prep/live_copilot/` |

**Stays as it is** (R2 moved the code into `core/` and `control_plane/`): `core/`, `contract/`, `control_plane/guardrails/`, `lifecycle_kit/`, `control_plane/triggers/`, `control_plane/people_surface/`, `control_plane/company_memory/`, `control_plane/connectors/` (books, spend, meeting, slack, people, event lookup, tool reply, meetings to memory, memory views), `market_simulation/`, `render.log`.

## 8. Out of scope

- Real Fathom webhooks, Gmail, Drive or Slack connectors. Sources arrive from files on a simulated clock.
- Speech to text. A live call is simulated as timed text lines.
- A real travel API, real bookings or payments. The fare source is simulated, and a booking only gets a simulated reference.
- Login and SSO. The role switcher is a demo control, not authentication.
- Embeddings or a vector database. Retrieval is deterministic (industry and tag match).
- The learning loop (v1 ticket T21), the chief-of-staff agent, the relay sandbox, Claude on Vertex.
- Pricing (the focus group asked for flat pricing; this is a business decision, not a build item).
- Any per-person score, ranking or performance view.

**Planned, not built: any document type in the brain inbox (owner, Oct 19).** Today the inbox reads Fathom transcripts (JSON), Word (.docx), email (.eml), chat exports and live call lines. Later it must read any document people send: Excel and CSV sheets, PDF (including scanned PDF through OCR), PowerPoint, Google Docs and Sheets exports, images of whiteboards, and plain text. The plan: one reader per format in `control_plane/company_brain/source_readers.py`, each turning the file into numbered lines with a location (sheet and cell, page and line, slide), so every fact still links to its exact source. Tables keep their row and column as the location.

## 9. Risks

| Risk | What we do |
|---|---|
| The fake Cleaner translates by a fixture lookup, so exams do not measure translation quality | Say so in RESULTS. Record one real Sonnet sample per source kind, only with Pratham's OK |
| Parallel tickets code against contracts the other side has not built yet | Contracts are frozen in `TICKETS_v2.md`. After each wave the lead runs the full suite and sends any break back to its owner |
| New prospect clients change counts that old tests assert | Data ticket adds clients C07 to C10 only. RBAC ticket makes client-count asserts read the database |
| Library leaks client details | Only the Playbook writer writes there. Its check step blocks contact names, emails, phone numbers and salary words |
| Real Sonnet is too slow for a live call | The live path uses code only. The model runs at the end of the call |
| The console rewrite is large | Pages are plug-ins with one owner each. The shell has its own ticket |
| The test run grows past 3 minutes | Brain tests use a small sample memory, not the full pipeline. Full pipeline runs only in exams |
