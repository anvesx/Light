# S3 — import company-os into Light — evidence

Worktree: `Light-company-os`, branch `feat/company-os`, base `main` @ `a0f33b5`. Source: `anvesx/company-os` @ `ed8eea6` (2026-10-22), no uncommitted changes.

## 1. Copy

The tracked files were copied the same way as S1: `git ls-files` from the source, then `rsync --files-from`.

- Source tracked files: 326. Files staged under `company-os/`: 326.
- No file under `company-os/` matches Light's root `.gitignore`. `company-os/.gitignore` came along and keeps its own rules (databases, the local-only web console).
- Nothing outside `company-os/` changed in the copy. FEATURES.md, README.md, STATUS.md and this file were edited afterwards, by hand.

## 2. Tests, unchanged in place

```
$ cd company-os && python3 -m unittest discover -s tests -t .
Ran 483 tests in 36.251s
OK (skipped=4)
```

## 3. Exams, unchanged in place

```
$ cd company-os && python3 -m evaluation.run_all_exams
exit 0 — 10 PASS, 0 FAIL
meeting_prep, deal_brief, live_copilot, finance_watch, spend_advisor, travel_booking,
brain_cleaner, brain_extractor, brain_linker, brain_playbook
```

All exams use the fake model, so they need no network and no API key. The run rewrites `evaluation/latest_scores.json`; that file was restored to the copied version afterwards.

## 4. Known gaps

- `company-os/` is a separate lane for now. Nothing in `orb/` or `fleet/` imports it, and it imports nothing from them.
- The company brain (`company-os/control_plane/company_brain/`) is to be handed to its own repo. FEATURES.md also says the org-wide knowledge DB lives outside `Light/`.
- `orb/AGENTS.md` and `orb/CLAUDE.md` point to a "Company-OS constitution" at `../../../Company-OS/AGENTS.md`, outside this repo. That is a different thing with a similar name.
