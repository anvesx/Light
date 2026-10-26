---
name: deal_brief
description: Prepares a growth person for a live deal from the deal's own items and redacted playbooks. Use it when a person asks for a brief on a deal.
family: meeting_prep
tools: [deal_overview, similar_playbooks, kickoff_checklist, send_private_message]
starter_roles: [ceo, growth, rnd_lead]
approver_roles: [ceo]
reads_library: true
---

# deal brief

Start here. The files of this folder:

- `instructions.md`: the system prompt.
- `guardrails.md`: what the agent must never do. Code guards still enforce the rules.
- `memory.md`: which memory areas it reads and writes.
- `graph.json`: what it does in each lifecycle step.
- `experience.md`: approved lessons from past runs.
- `pack.py`: the lifecycle code. `README.md`: how it works.
