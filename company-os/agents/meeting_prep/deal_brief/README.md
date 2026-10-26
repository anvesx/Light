# Deal brief agent

Prepares Growth for a live deal, for example C07 CareNest. Started by growth, ceo or rnd_lead. It reads the library (`reads_library = True`).

**It gives.** Similar past clients (from redacted playbooks only), ideas to close tied to a lesson, risks, and a kickoff checklist of questions that past clients raised late.

**Rules.** Every point cites a playbook id (`PB-...`) or an item of this deal's own area. Items the brain is unsure of are labelled "Unconfirmed". The check step blocks unknown cites, other clients' items, contact names and emails. It never reads another client's raw items, finance or project data.

**Tools.** `deal_overview` (own area), `similar_playbooks` and `kickoff_checklist` (library), in `control_plane/connectors/deal_brain_tools.py`. Code picks the similar deals and the checklist; the model writes the ideas and questions.

Files: `pack.py`, `fake_brain.py`, `exam/replay_exam.py` (with `judge`), `exam/exam_fixture.py` (stand-in library built from the answer keys, used only when the brain has no playbooks).
Run the exam: `python3 -m agents.meeting_prep.deal_brief.exam.replay_exam`.

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

Other folders: `exam/`: `replay_exam.py`, `exam_fixture.py`.
