---
name: brain_playbook
description: Turns a closed deal into a redacted playbook and kickoff checklist questions for the library. Use it when a deal is won or lost.
family: company_brain
tools: [brain_read_deal, brain_publish_playbook, brain_save_checklist]
starter_roles: [ceo, finance_lead, growth, rnd_lead, system]
approver_roles: [ceo]
reads_library: false
---

# brain playbook

Start here. The files of this folder:

- `instructions.md`: the system prompt.
- `guardrails.md`: what the agent must never do. Code guards still enforce the rules.
- `memory.md`: which memory areas it reads and writes.
- `graph.json`: what it does in each lifecycle step.
- `experience.md`: approved lessons from past runs.
- `pack.py`: the lifecycle code. `README.md`: how it works.
