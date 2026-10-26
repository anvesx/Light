**Role in the harness:** The travel booking agent: a person asks for flights (and a hotel) for N people, the agent shows the best 3 of each under the travel policy, and the booking waits for an Admin.

# Travel booking

Any starter role (ceo, rnd_lead, finance_lead, csm, growth) may ask. Only ceo and finance_lead may approve.

## Flow

1. `scripts/service.py`: `service.request_trip(cos, caller_id, request)` reads the request (words or a dict), runs the agent in area `devx-internal`.
2. The agent searches `control_plane/connectors/fare_search.py`, ranks with `scripts/policy_ranking.py`, and writes one letter to the asker (kind `travel_options`).
3. It then calls `book_travel` (risky), so the run ends `held` with one approval. Option 1 of each is the default.
4. `service.choose_options(...)` swaps the held approval for one with other shown options.
5. After an Admin approves, `service.booking_after_approval(cos, approval_id)` books once and gives a `SIM-` reference.

## Files

| File | What it does |
|---|---|
| `scripts/travel_policy.json` | Economy under 2.5 hours, departure window 6 AM to 9 PM, show top 3. Hotel rates come from `POLICY_RATE`. |
| `scripts/policy_ranking.py` | Policy first, then cheapest. Adds `policy_ok`, `why`, `total_inr`. |
| `scripts/request_parser.py` | Words or dict to a checked request. Errors are plain sentences. |
| `scripts/booking_store.py`, `scripts/schema.sql` | Tables `travel_requests` and `travel_bookings` on `cos.memory.conn`. |
| `tools/book_travel.py` | The risky `book_travel` tool. It runs only after an Admin approves. |
| `pack.py`, `fake_brain.py` | The agent pack and its deterministic stand-in model. The check step blocks out-of-policy options, wrong totals and names. |
| `exam/replay_exam.py`, `exam/exam_requests.json` | The exam: 8 requests, policy, totals, approval gate. |

## Notes

With a return date the agent also searches the return flight, ranks it by the same policy, and shows the best 3 round trips (both flight numbers, total per person and per group). Booking and `choose_options` then use the round-trip option id. `flights` still holds the outbound top 3. A hotel is shown only when a return date (or "for N nights") is given. The fare source is simulated, and a booking gets only a simulated reference.

## Agent folder

| File | What it holds |
|---|---|
| `agent.md` | Name, description, family, tools, roles. Read this first. |
| `instructions.md` | The system prompt. |
| `guardrails.md` | What the agent must never do. The code guards still enforce the rules. |
| `memory.md` | The memory areas it reads and writes, and why. |
| `graph.json` | What it does in each lifecycle step. |
| `experience.md` | Approved lessons from past runs. The newest 20 go into the prompt. |
| `pack.py`, `fake_brain.py` | The lifecycle code and the stand-in for the model. |
| `exam/` | `replay_exam.py` and its data. |

Other folders: `scripts/`: `booking_store.py`, `policy_ranking.py`, `request_parser.py`, `service.py`, `schema.sql`, `travel_policy.json`. `tools/`: `book_travel.py`. `exam/`: `replay_exam.py`, `exam_requests.json`.
