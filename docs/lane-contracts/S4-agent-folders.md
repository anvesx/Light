# S4: Agent folders and lessons (company-os)

**Feature:** every `company-os` agent is one folder with the same files, and agents learn from failed checks.
**Repo:** `company-os`
**Branch:** `feat/company-os`

---

## Task

Put the parts of each agent in files a person can read. Add a lessons file, so an agent can use what past runs taught. Ten agents change: six under `company-os/agents/` and four under `company-os/control_plane/company_brain/agents/`. The list is `AGENTS` in `company-os/wiring/agent_registry.py`.

## Layout of one agent folder

| Path | What it holds |
|---|---|
| `agent.md` | Frontmatter: name, description, family, tools, starter_roles, approver_roles, reads_library. A short body. |
| `instructions.md` | The system prompt, moved word for word out of `pack.py`. |
| `guardrails.md` | What the agent must never do (bullets). The code guards still enforce the rules. |
| `memory.md` | The memory areas it reads and writes, and why. |
| `graph.json` | One line per lifecycle step: record, understand, decide, check, act, remember. |
| `experience.md` | Approved lessons. Starts with no lessons. |
| `tools/`, `scripts/` | Only where the agent has its own tool code or helper modules (`travel_booking`, `live_copilot`). |
| `exam/` | `replay_exam.py` and its data files. |
| `pack.py`, `fake_brain.py`, `README.md` | Stay at the root. The registry imports the first two. |

## Interface change

- New `lifecycle_kit/agent_folder.py`: finds a pack's folder, parses `agent.md` (standard library only), builds the prompt, and `check_agent_folder(folder, name, pack)` returns a list of problems.
- `AgentPack.system_prompt()` default is `instructions.md`, then the bullets of `guardrails.md`, then the newest 20 bullets of `experience.md`. A pack outside an agent folder gets an empty prompt.
- New `lifecycle_kit/lessons.py`: `LessonLog` writes one candidate per problem of a failed `check` step to `lesson_candidates.jsonl`; `promote_candidate(...)` adds a person's lesson text to `experience.md`. A small CLI wraps both.
- `LifecycleRunner(runtime, lessons=None)`: the log is optional. `build_company_os` passes `LessonLog(<state_dir>/lessons)`.
- `evaluation/run_all_exams.py` imports `{package}.exam.replay_exam`.

## Killed alternatives

### Alternative 1: write candidates into the agent folder
- **Why killed:** every test run with a failed check would change files in the source tree. Candidates go to the runtime store. Only a person's promotion writes to `experience.md`.

### Alternative 2: add a YAML library for `agent.md`
- **Why killed:** the repo has no packages to install. The frontmatter holds only `key: value` lines and inline lists, so a small parser is enough.

### Alternative 3: move the shared connector tools into each agent folder
- **Why killed:** several agents share those tools, and the guardrail tests point at them. Only code that lived in `pack.py` or beside it moved (`book_travel` and the travel and live call helpers).

## Not changed

- Model behaviour: the prompt text is the same. The model now also sees the guardrail bullets, and later the approved lessons.
- The code guards (`check` steps, role scopes, approvals).
- `experiments/`: those packs override `system_prompt()` and are not in the registry.

## Verify

```
cd company-os
python3 -m unittest discover -s tests -t .
python3 -m evaluation.run_all_exams
git status --short        # no file written by the tests
```
