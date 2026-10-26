---
name: live_copilot
description: Suggests the next question while a client call plays and writes a short summary at the end. Use it during a live call.
family: meeting_prep
tools: [live_call_script, live_call_brain]
starter_roles: [ceo, csm, finance_lead, growth, rnd_lead]
approver_roles: [ceo, csm]
reads_library: true
---

# live copilot

Start here. The files of this folder:

- `instructions.md`: the system prompt.
- `guardrails.md`: what the agent must never do. Code guards still enforce the rules.
- `memory.md`: which memory areas it reads and writes.
- `graph.json`: what it does in each lifecycle step.
- `experience.md`: approved lessons from past runs.
- `pack.py`: the lifecycle code. `README.md`: how it works.
