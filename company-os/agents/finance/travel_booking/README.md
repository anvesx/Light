**Role in the harness:** The travel booking agent: a person asks for flights (and a hotel) for N people, the agent shows the best 3 of each under the travel policy, and the booking waits for an Admin.

# Travel booking

Any starter role (ceo, rnd_lead, finance_lead, csm, growth) may ask. Only ceo and finance_lead may approve.

## Flow

1. `service.request_trip(cos, caller_id, request)` reads the request (words or a dict), runs the agent in area `devx-internal`.
2. The agent searches `control_plane/connectors/fare_search.py`, ranks with `policy_ranking.py`, and writes one letter to the asker (kind `travel_options`).
3. It then calls `book_travel` (risky), so the run ends `held` with one approval. Option 1 of each is the default.
4. `service.choose_options(...)` swaps the held approval for one with other shown options.
5. After an Admin approves, `service.booking_after_approval(cos, approval_id)` books once and gives a `SIM-` reference.

## Files

| File | What it does |
|---|---|
| `travel_policy.json` | Economy under 2.5 hours, departure window 6 AM to 9 PM, show top 3. Hotel rates come from `POLICY_RATE`. |
| `policy_ranking.py` | Policy first, then cheapest. Adds `policy_ok`, `why`, `total_inr`. |
| `request_parser.py` | Words or dict to a checked request. Errors are plain sentences. |
| `booking_store.py`, `schema.sql` | Tables `travel_requests` and `travel_bookings` on `cos.memory.conn`. |
| `pack.py`, `fake_brain.py` | The agent pack and its deterministic stand-in model. The check step blocks out-of-policy options, wrong totals and names. |
| `replay_exam.py`, `exam_requests.json` | The exam: 8 requests, policy, totals, approval gate. |

## Notes

With a return date the agent also searches the return flight, ranks it by the same policy, and shows the best 3 round trips (both flight numbers, total per person and per group). Booking and `choose_options` then use the round-trip option id. `flights` still holds the outbound top 3. A hotel is shown only when a return date (or "for N nights") is given. The fare source is simulated, and a booking gets only a simulated reference.
