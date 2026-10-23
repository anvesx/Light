# linker

**Role in the harness:** Brain agent 3. It connects the new items of one source to older items, projects and deals. Code decides the links (`control_plane/company_brain/link_rules.py`); the model only confirms.

- Run: caller `system`, trigger `event`, area of the source, inputs `{"source_id"}`.
- Links: `supersedes`, `contradicts` (newer wins, older becomes `superseded` through `resolve_contradiction`), `same_as` (evidence moves to the older item, the repeat becomes `resolved`), `answers`, `refines`, `follows_up`.
- Tools: `control_plane/company_brain/link_tools.py`. Each refuses items outside the run's area.
- Exam: `replay_exam.py` loads the sources, stores the answer-key items, links them and compares with the key. A link is wrong when it reverses a key link or is a `supersedes` or `contradicts` the key does not have. Extra `answers`, `same_as` and `refines` links are listed, not counted as wrong.
