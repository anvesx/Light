---
name: travel_booking
description: Finds flights and hotels, ranks them by the travel policy, shows the best three and holds the booking for an Admin to approve. Use it when a person asks for a trip.
family: finance
tools: [search_flights, search_hotels, book_travel, send_private_message]
starter_roles: [ceo, csm, finance_lead, growth, rnd_lead]
approver_roles: [ceo, finance_lead]
reads_library: false
---

# travel booking

Start here. The files of this folder:

- `instructions.md`: the system prompt.
- `guardrails.md`: what the agent must never do. Code guards still enforce the rules.
- `memory.md`: which memory areas it reads and writes.
- `graph.json`: what it does in each lifecycle step.
- `experience.md`: approved lessons from past runs.
- `pack.py`: the lifecycle code. `README.md`: how it works.
