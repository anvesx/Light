# Store watch agent (fraud_watch)

## What it watches
Every day it reads the retail client's store activity for the last 30 days and compares each staff member with the rest of their store. It looks for three unusual patterns:
- **Many cash refunds:** 5 or more cash refunds by one person, at least 3 times the store's normal per person.
- **Discounts approved by the person who asked for them:** 2 or more, at least 3 times the store's normal (normal staff have none).
- **Repeated free remakes:** 5 or more free remakes by one person, at least 3 times the store's normal.

It does not flag a store-wide wave of card refunds with the reason "recall", or one manager approving many discounts in a sale week. Those are spread across many people or are normal approvals, so the rules above do not match them.

## When it acts
It runs on a timer or when the retail client's CSM (or the CEO) asks. If nothing is unusual, it stays quiet and makes no model call.

## Who it tells, and why not the store manager
It sends one private message to the retail client's DevX CSM. Store managers are client staff, and our guard lets agents message DevX people only. The CSM reviews the evidence and talks to the store manager.
The agent may also propose a follow-up (for example "review these refunds with the store manager"). A follow-up waits for the approval of a CSM or the CEO.

## What it may never do
- Accuse anyone, or say what a person meant to do. It says "unusual pattern" and shows the evidence.
- Use the words "fraud", "theft", "stealing" or "cheating" (or close forms). A check stops the run before any message is sent.
- Message anyone who is not the client's DevX CSM.
- Read any other client's data.

## Tools
`refunds_by_staff`, `discounts_by_staff`, `remakes_by_staff` (read), `send_private_message`, `create_followup_task` (needs approval).

## How it is scored
The replay exam scans every day from 2026-05-01 to today. A planted case is "found" when the agent first shows it on or after the first date a simple rule could see it (days late are reported). A look-alike that gets flagged counts as a false alarm. Scores go to company memory (`found`, `missed`, `false_alarms`). Current result: 3 of 3 found, 0 false alarms.
