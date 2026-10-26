# Memory map

Which store areas this agent reads and writes, and why. Role scopes decide which areas a run may read.

## Reads

- Flights and hotels from the fare search tools (`search_flights`, `search_hotels`).
- The travel policy file `scripts/travel_policy.json`.

## Writes

- The tables `travel_requests` and `travel_bookings` in company memory (`scripts/booking_store.py`).
- One private letter to the asker, kind `travel_options` (`send_private_message`).
- The booking itself (`book_travel`). It is risky and runs only after an Admin approves.

## Why

- The request and its options must be stored, so the approver sees the same options the letter showed.
- A booking spends money, so an Admin approves and the tool checks the total again.
