# Memory map

Which store areas this agent reads and writes, and why. Role scopes decide which areas a run may read.

## Reads

- Company books data: invoices, payments, budget against spend and travel share of salary (`invoices_window`, `payments_window`, `budget_vs_spend`, `travel_share_of_salary`).

## Writes

- A case in the internal area `devx-internal` for each finding (`add_case`).
- One private message to the finance lead (`send_private_message`).
- A follow-up task in company memory (`create_followup_task`). It is risky and waits for approval.

## Why

- Finding problems needs the books. Cases keep a record, so the same finding is not reported twice.
- A task changes memory, so a person approves it first.
