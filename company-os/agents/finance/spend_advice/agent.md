---
name: spend_advisor
description: Answers a leader's finance question with a cost breakdown, a verdict for every trip and concrete savings. Use it when a leader asks about spend.
family: finance
tools: [spend_breakdown, trip_savings, trip_verdicts, travel_by_team, trip_alternatives, send_private_message]
starter_roles: [ceo, finance_lead, rnd_lead]
approver_roles: []
reads_library: false
---

# spend advisor

Start here. The files of this folder:

- `instructions.md`: the system prompt.
- `guardrails.md`: what the agent must never do. Code guards still enforce the rules.
- `memory.md`: which memory areas it reads and writes.
- `graph.json`: what it does in each lifecycle step.
- `experience.md`: approved lessons from past runs.
- `pack.py`: the lifecycle code. `README.md`: how it works.
