# Cleaner agent (`brain_cleaner`)

**Role in the harness:** First internal brain agent. It makes clean English lines for one stored source.

- Code removes filler and fixes speaker names from the participants.
- The model translates non-English lines. The fake brain looks them up in `translations.json`.
- A line it cannot translate keeps its raw text, gets a `translation` row on the check list and still goes to the Extractor. Nothing waits for a person.
- Raw text never changes (the store refuses it). No line is dropped.
- Tools: `brain_read_source`, `brain_save_clean_lines`, `brain_queue_review` (`control_plane/company_brain/write_tools.py`). Each refuses a source outside the run's area.
- Exam: `exam/replay_exam.py` (every non-English line has clean text or a review entry, 0 dropped, raw unchanged).

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
