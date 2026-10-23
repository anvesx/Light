# Delivery progress agent

**Role in the harness:** Delivery progress agent: works out real progress against the signed SOW from git evidence (not from what people report), saves a progress snapshot per project into company memory, and tells the project's CSM privately about unbilled work, rework and a late project.

CSMs are DevX's project managers. The agent never measures or ranks individual developers: no PR counts or lines per person appear anywhere.

**What it works out** (the code decides, the model only explains):
- Each SOW scope item is *not started*, *in progress*, *done* (all linked tasks done, linked PRs merged and deployed to production) or *at risk* (past its due date and not done).
- The finish date at the current pace, against the planned end. Pace is measured on the latest Monday: share of linked scope hours merged against share of the calendar used.
- Each project is *on track*, *at risk* or *behind*.

**What it tells the CSM** (one private message per CSM):
- **Unbilled work:** 3 or more merged PRs that link to no task or scope item. Small chores (under 30 lines, or titled "chore") are ignored.
- **Rework:** one scope item changed 4 or more times after client meetings.
- **Behind deadline:** 30% or more of the calendar used and the merged share is under 60% of the calendar share.
The same flag is not sent again within 7 days.

**What it writes:** one progress snapshot per project per run (`kind="progress_snapshot"`, JSON text) in the client's area. This is the project progress feed. `connectors/progress_views.py` shows it by role. Each flag is also saved as a case.

**When it acts:** every day on a timer for each client (all its projects), and when a PR merges (trigger kind `event`, input `pr_id`; this run covers that PR's project). A CSM, project lead, CEO or CTO can also ask for a run. Every run makes one model call to write headlines.

**What it may never do:** message anyone outside DevX, read another client's data, or name or count developers. Before anything is saved or sent, a check confirms every number, date and id matches what the code found, and that no person is named.

**Tools:** `scope_burndown`, `unlinked_merged_prs`, `project_pace` (read); `send_private_message`.

**How it is scored:** `replay_exam.py` replays each client day by day from 2026-08-10 to today and compares with the planted cases DEL-1 (unbilled work), DEL-2 (rework) and DEL-3 (behind deadline): found or missed, days late against the first day a case could be seen, and false alarms on the look-alikes DEL-L1 (small chores), DEL-L2 (two revisions) and DEL-L3 (on track). Scores are saved in company memory.

## Files in this folder

| File | What it does |
|---|---|
| `__init__.py` | Marks the folder as a Python package. |
| `fake_brain.py` | Stand-in for the model, for tests and demos: writes headlines and plain-English flags from the data. |
| `pack.py` | The agent: reads git evidence, computes statuses and signals, checks the text, messages the CSM and writes snapshots. |
| `replay_exam.py` | Replays history day by day and scores the agent against the planted delivery cases. |
