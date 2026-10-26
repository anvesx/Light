---
name: meeting_prep
description: Prepares the DevX attendees of a client meeting. Use it before a meeting (a timer starts it in the 24 hours before, or a person asks) to list what must be settled with the client.
family: meeting_prep
tools: [upcoming_meeting, project_open_items, project_recent_decisions, project_brain_items, recent_client_messages, send_private_message]
starter_roles: [ceo, csm, growth, project_lead, rnd_lead, system]
approver_roles: [ceo, csm]
reads_library: false
---

# meeting prep

Start here. The files of this folder:

- `instructions.md`: the system prompt.
- `guardrails.md`: what the agent must never do. Code guards still enforce the rules.
- `memory.md`: which memory areas it reads and writes.
- `graph.json`: what it does in each lifecycle step.
- `experience.md`: approved lessons from past runs.
- `pack.py`: the lifecycle code. `README.md`: how it works.
