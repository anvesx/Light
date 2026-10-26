---
name: finance_watch
description: Reads the books each day and tells the finance lead about duplicate invoices, large payments to new vendors, budget overruns and travel cost. Use it on the daily timer or when the finance lead asks.
family: finance
tools: [invoices_window, payments_window, budget_vs_spend, travel_share_of_salary, send_private_message, create_followup_task]
starter_roles: [ceo, finance_lead, system]
approver_roles: [ceo, finance_lead]
reads_library: false
---

# finance watch

Start here. The files of this folder:

- `instructions.md`: the system prompt.
- `guardrails.md`: what the agent must never do. Code guards still enforce the rules.
- `memory.md`: which memory areas it reads and writes.
- `graph.json`: what it does in each lifecycle step.
- `experience.md`: approved lessons from past runs.
- `pack.py`: the lifecycle code. `README.md`: how it works.
