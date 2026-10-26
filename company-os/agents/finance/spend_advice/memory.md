# Memory map

Which store areas this agent reads and writes, and why. Role scopes decide which areas a run may read.

## Reads

- Trips, fares, savings, verdicts and team travel data from the company data (`spend_breakdown`, `trip_savings`, `trip_verdicts`, `travel_by_team`, `trip_alternatives`).

## Writes

- One private message to the person who asked, kind `finance_answer` (`send_private_message`). No memory item is written.

## Why

- Code computes every number. The agent needs read access to the books only.
- It acts only for the internal area `devx-internal`.
