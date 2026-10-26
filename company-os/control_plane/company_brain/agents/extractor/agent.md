---
name: brain_extractor
description: Turns the clean lines of a source into items (decisions, requirements, blockers, questions, commitments, money, risks, sentiment) with source spans. Use it after the cleaner.
family: company_brain
tools: [brain_read_source, brain_add_items]
starter_roles: [ceo, finance_lead, rnd_lead, system]
approver_roles: [ceo]
reads_library: false
---

# brain extractor

Start here. The files of this folder:

- `instructions.md`: the system prompt.
- `guardrails.md`: what the agent must never do. Code guards still enforce the rules.
- `memory.md`: which memory areas it reads and writes.
- `graph.json`: what it does in each lifecycle step.
- `experience.md`: approved lessons from past runs.
- `pack.py`: the lifecycle code. `README.md`: how it works.
