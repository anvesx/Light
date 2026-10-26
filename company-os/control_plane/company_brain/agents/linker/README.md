# linker

**Role in the harness:** Brain agent 3. It connects the new items of one source to older items, projects and deals. Code decides the links (`control_plane/company_brain/link_rules.py`); the model only confirms.

- Run: caller `system`, trigger `event`, area of the source, inputs `{"source_id"}`.
- Links: `supersedes`, `contradicts` (newer wins, older becomes `superseded` through `resolve_contradiction`), `same_as` (evidence moves to the older item, the repeat becomes `resolved`), `answers`, `refines`, `follows_up`.
- Tools: `control_plane/company_brain/link_tools.py`. Each refuses items outside the run's area.
- Exam: `exam/replay_exam.py` loads the sources, stores the answer-key items, links them and compares with the key. A link is wrong when it reverses a key link or is a `supersedes` or `contradicts` the key does not have. Extra `answers`, `same_as` and `refines` links are listed, not counted as wrong.

## Agent folder

| File | What it holds |
|---|---|
| `agent.md` | Name, description, family, tools, roles. Read this first. |
| `instructions.md` | The system prompt. |
| `guardrails.md` | What the agent must never do. The code guards still enforce the rules. |
| `memory.md` | The memory areas it reads and writes, and why. |
| `graph.json` | What it does in each lifecycle step. |
| `experience.md` | Approved lessons from past runs. The newest 20 go into the prompt. |
| `pack.py`, `fake_brain.py` | The lifecycle code and the stand-in for the model. |
| `exam/` | `replay_exam.py` and its data. |
