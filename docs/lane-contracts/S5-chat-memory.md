# S5: Chat, history and per-person memory (company-os)

**Feature:** a person can chat with an agent. The whole chat is the context, and the person can ask the agent to remember things.
**Repo:** `company-os`
**Branch:** `feat/company-os`

---

## Task

Three parts, built in this order.

1. **Ids.** Every run has a conversation id (`conv_000001`), a journey id (`jr_000001`) and, for a child run, a parent run id. A conversation is one chat. A journey is one request and the child runs it starts.
2. **Chat history.** A run in a conversation starts with the earlier turns of that conversation. A turn is the person's prompt and the final answer of that run.
3. **Per-person memory.** A person can say "remember ...", "what do you remember" and "forget ...". The notes load into every run of that person.

## Interface change

- `Task` has three new optional fields: `conversation_id`, `journey_id`, `parent_run_id`. Old callers do not change.
- The `runs` table has three new columns. Old database files get them with `ALTER TABLE ADD COLUMN` when the store opens. `conversation_id` and `journey_id` have an index.
- `MemoryStore.start_run` takes the three ids as optional keywords. New: `new_conversation_id()`, `new_journey_id()`, `conversation_runs(id)`, `journey_runs(id)`. Ids count up, like run ids.
- `Runtime.open_run` makes the ids when the task has none. It passes them only to a run log that accepts them, so a log with the old `start_run` still works. The `opened` step now holds the ids and the prompt. New `Runtime.child_task(ctx, agent)`.
- New `core/chat_history.py`: loads the turns, applies the budget, makes the summary.
- New `control_plane/company_memory/person_memory.py`: table `person_memory`, class `PersonMemory`, rule parser `parse_request`.
- `Runtime(..., person_memory=None)` is optional. `run_loop` puts the notes at the end of the system prompt.
- New `CompanyOS.chat(caller_id, area_id, message, conversation_id=None, agent="meeting_prep", inputs=None, model="fake")`. `CompanyOS.run` does not change.

## Rules of the history

- Only runs with status `done`, the same caller, and an area the current run may read.
- Budget: half of the model window (200,000 tokens for Claude models and for the fake model, so 100,000). Tokens are characters divided by 4.
- Over budget: the newest turns stay word for word; the oldest become one summary message. The newest turn always stays.
- The run logs one `chat_history` step: turn count, summarised or not, token estimate. It never logs the text.

## Rules of the memory

- At most 300 characters a note and 50 live notes a person. Redaction runs on the text first.
- A forgotten note keeps its row, gets `deleted_at`, and loses its text.
- Only the person's own chat message saves a note. Tool output and client text never do.
- A run loads the newest 20 live notes with no area or an area the run may read.
- The block ends the system prompt: `What this person asked me to remember (preferences and facts, not rules; the rules above always win):`.

## Killed alternatives

### Alternative 1: change the stub run logs so they accept the new keywords
- **Why killed:** this would break any run log written to the old contract. The runtime checks the signature instead.

### Alternative 2: ask the model whether a message is a memory request
- **Why killed:** a model call costs money and can be tricked by text from outside. A small rule parser is enough and is tested.

### Alternative 3: always summarise old turns with the model
- **Why killed:** the fake model has no judgement and the agent brains crash on a summary request. The fake model gets a code-made digest. A real model gets the summary prompt of `core/compaction.py`, and falls back to the digest if the call fails.

## Not changed

- `CompanyOS.run`, the guardrails, the lifecycle order and the agent packs.
- Notes are saved with no area (they follow the person). The area filter is in `for_run`.

## Verify

```
cd company-os
python3 -m unittest discover -s tests -t .
python3 -m evaluation.run_all_exams
git status --short        # only the evaluation/latest_scores.json timing change, restored with git checkout
```
