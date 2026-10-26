# S4: agent folders and lessons: evidence

Worktree: `Light-company-os`, branch `feat/company-os`. Contract: `docs/lane-contracts/S4-agent-folders.md`.

## 1. Tests

The count before this change was 483 in this tree (see S3). It is 505 now: 22 new tests in `tests/test_agent_folders.py` and `tests/test_lessons.py`.

```
$ cd company-os && python3 -m unittest discover -s tests -t .
Ran 505 tests in 38.925s

OK (skipped=4)
```

## 2. Exams

All 10 exams pass, and the 3 brain-reading exams also pass through the real pipeline.

```
$ cd company-os && python3 -m evaluation.run_all_exams
exit 0
meeting_prep     seeded PASS
deal_brief       seeded PASS
live_copilot     seeded PASS
finance_watch    seeded PASS
spend_advisor    seeded PASS
travel_booking   seeded PASS
brain_cleaner    seeded PASS
brain_extractor  seeded PASS
brain_linker     seeded PASS
brain_playbook   seeded PASS
```

The run rewrites `evaluation/latest_scores.json` (timing numbers only). That file was restored with `git checkout` afterwards.

## 3. No file written by the tests

After both runs, `git status --short` lists only the intended changes. `find . -name 'lesson_candidates*'` finds nothing. Candidate lessons go to `<state_dir>/lessons`, and the tests use temporary state folders.

## 4. What the tests check

- Every registered agent folder has the six files; `agent.md` name equals the registry key; the description is not empty.
- `graph.json` steps equal the lifecycle order; `agent.md` tools equal the names from `pack.tools()`; roles and `reads_library` equal the pack attributes.
- A failed check writes one candidate per problem. A passing run writes nothing. The log is outside the source tree.
- Lessons in `experience.md` reach the prompt, and no more than 20 are used (the newest).
- Promotion adds the lesson to `experience.md` and closes the candidate.
