---
name: brain_linker
description: Links the new items of a source to older items, projects and deals. Use it after the extractor.
family: company_brain
tools: [brain_read_source_items, brain_set_scope, brain_add_links, brain_set_state]
starter_roles: [ceo, csm, finance_lead, growth, rnd_lead, system]
approver_roles: [ceo]
reads_library: false
---

# brain linker

Start here. The files of this folder:

- `instructions.md`: the system prompt.
- `guardrails.md`: what the agent must never do. Code guards still enforce the rules.
- `memory.md`: which memory areas it reads and writes.
- `graph.json`: what it does in each lifecycle step.
- `experience.md`: approved lessons from past runs.
- `pack.py`: the lifecycle code. `README.md`: how it works.
