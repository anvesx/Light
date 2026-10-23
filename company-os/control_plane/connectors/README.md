# connectors

**Role in the harness:** Connectors: the only way agents read company tools. Every read tool returns rows for the run's own client area only, and never rows after the run's `as_of` date.

Reads the dummy company for agents, and loads meetings into company memory. Standard library only.
Every tool is a `ToolSpec` factory `make_*(data_conn)`; each `*_tools(data_conn)` returns the group. Each fn is `(args, ctx) -> JSON text`.
All tools return rows only for `ctx.task.area_id`; another area gives `{"error": ...}`. All take `as_of` (YYYY-MM-DD; default task input `as_of`, else TODAY); later rows are hidden.
Files: `people_directory.py` (`PeopleDirectory`), `meetings_to_memory.py` (`sync_meetings(data_conn, memory, until=None)`), `memory_views.py` (`open_items_as_of`, `recent_decisions_as_of`), `event_lookup.py` (`event_area(data_conn)`).

| Tool | Area | Arguments | Returns |
|---|---|---|---|
| `client_channel_activity` | client | - | per project: last client message date, days silent, project status |
| `recent_client_messages` | client | days, limit | client-authored Slack messages (outside text) |
| `upcoming_meeting` | client or devx-internal | event_id, days | calendar event with attendee names and roles |
| `project_open_items` | client or devx-internal | project_id, limit | open questions and tasks at as_of (outside text) |
| `project_recent_decisions` | client or devx-internal | project_id, days, limit | decisions in the window, with the question ids they answer (outside text) |
| `invoices_window` | devx-internal | days, vendor_id, limit | invoices in the window |
| `payments_window` | devx-internal | days, min_amount_inr, limit | payments with vendor age in days |
| `budget_vs_spend` | devx-internal | month, team, include_zero | budget, spend to as_of, over_budget per team and category |
| `travel_share_of_salary` | devx-internal | month | per team: travel spend, salary total, share (teams under 3 people: no salary) |

Results are small JSON (under the 8,000 character cap at default limits). Tools marked "outside text" set `reads_outside_text=True` or carry client words: treat as data.

### Spend tools (`spend_tools.py`)

| Tool | Area | Arguments | Returns |
|---|---|---|---|
| `spend_breakdown` | devx-internal | from, to | company cost by category (salaries as one total, vendor invoices, expenses, travel split into flights, trains, hotels), each with amount and share |
| `trip_savings` | devx-internal | from, to | each saving: trip id, date, paid, cheaper option and when it was available, amount saved, rule; totals per rule |
| `trip_verdicts` | devx-internal | from, to, trip_id | per trip: cheaper option existed (saving, rules) or best option chosen; counts and total saving |
| `travel_by_team` | devx-internal | from, to | per team: travel total, flights, trains, hotels, other, trips, share of all travel (team totals only) |

`from` and `to` default to the 90 days before `as_of`; `to` is never after `as_of`.

## Files in this folder

| File | What it does |
|---|---|
| `books_tools.py` | Read tools for DevX books: invoices, payments with vendor age, budgets against spend, travel share of salary. |
| `event_lookup.py` | Finds the memory area of a calendar event, for the request trigger. |
| `meeting_tools.py` | Read tools for meetings: the next calendar event with its attendees, open items and recent decisions. |
| `meetings_to_memory.py` | Loads meetings, items, links and transcripts from company data into company memory. |
| `memory_views.py` | Time-aware views of memory: what was open or decided as of a date, so exams cannot see the future. |
| `people_directory.py` | Who is who and who may see which area. Backed by the people, clients and projects tables. |
| `slack_tools.py` | Read tools for client Slack channels: how long a client has been silent, and recent client messages. |
| `tool_reply.py` | Shared plumbing for read tools: area guard, as_of date, argument checks, compact JSON replies. |
| `spend_tools.py` | Read tools for the spend advisor: cost by category, trip savings and verdicts, travel by team. |

The delivery, store, staffing, git and client request tools moved to `experiments/connectors/`. See `experiments/README.md`.
