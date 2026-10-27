# S5: chat, history and per-person memory: evidence

Worktree: `Light-company-os`, branch `feat/company-os`. Contract: `docs/lane-contracts/S5-chat-memory.md`.

## 1. Tests

The count before this change was 505 (see S4). It is 539 now: 34 new tests in `tests/test_chat_memory.py`.

```
$ cd company-os && python3 -m unittest discover -s tests -t .
Ran 539 tests in 56.581s

OK (skipped=4)
```

`pytest` is not installed on this machine, so the suite was run with `unittest`. The tests are plain `unittest` classes.

## 2. Exams

All 10 exams pass, and the 3 brain-reading exams also pass through the real pipeline.

```
$ cd company-os && python3 -m evaluation.run_all_exams
meeting_prep     seeded PASS   (through real pipeline PASS)
deal_brief       seeded PASS   (through real pipeline PASS)
live_copilot     seeded PASS   (through real pipeline PASS)
finance_watch    seeded PASS
spend_advisor    seeded PASS
travel_booking   seeded PASS
brain_cleaner    seeded PASS
brain_extractor  seeded PASS
brain_linker     seeded PASS
brain_playbook   seeded PASS
```

The run rewrites `evaluation/latest_scores.json` (timing numbers only). That file was restored with `git checkout`.

## 3. What the tests check

- Ids are on the `runs` row and in the `opened` step, with the prompt. They count up without repeats.
- A follow-up in the same conversation keeps the conversation id and gets a new journey id.
- A child run keeps both ids and sets `parent_run_id`. `journey_runs` and `conversation_runs` find the runs.
- An old database file gets the columns and the two indexes. Opening it twice changes nothing.
- History loads for the same conversation, and not for a new one, another caller, or a run outside the area. Failed runs and runs without a prompt are skipped.
- Over budget, the oldest turns become one summary and the newest turn is word for word. The step holds counts only.
- Notes: remember, list, forget (soft delete, text cleared), private to one person, area filter, newest 20 per run, 300 and 50 limits, planted email and phone redacted.
- Tool output and client text that say "remember ..." save nothing.
- The notes block is the last part of the system prompt, and absent when there are no notes. The runtime works with no `PersonMemory`.
- A whole chat through `CompanyOS.chat`: turn 1 runs the agent, turn 2 sees turn 1 in its messages, a remember message saves a note, a new conversation has the note and no history, list and forget work, and a caller without access is refused.
