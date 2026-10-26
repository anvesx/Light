---
name: brain_cleaner
description: Makes clean English lines for one stored source: removes filler, fixes speaker names and translates other languages. Use it first when a new source arrives.
family: company_brain
tools: [brain_read_source, brain_save_clean_lines, brain_queue_review]
starter_roles: [ceo, finance_lead, rnd_lead, system]
approver_roles: [ceo]
reads_library: false
---

# brain cleaner

Start here. The files of this folder:

- `instructions.md`: the system prompt.
- `guardrails.md`: what the agent must never do. Code guards still enforce the rules.
- `memory.md`: which memory areas it reads and writes.
- `graph.json`: what it does in each lifecycle step.
- `experience.md`: approved lessons from past runs.
- `pack.py`: the lifecycle code. `README.md`: how it works.
