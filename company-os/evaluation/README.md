# evaluation

**Role in the harness:** Evaluation: scores every agent against planted cases, so we know if an agent is good enough, not only if it runs.

The dummy company has cases planted on purpose: a duplicate invoice, a project that is slipping, a refund pattern. It also has look-alikes that must not raise an alarm. Each agent pack has a replay exam (`agents/<name>/replay_exam.py`). The exam replays past days, runs the agent, and counts the cases it found, the cases it missed and the false alarms.

This folder runs all the exams together. Each exam gets its own fresh Company OS, so one exam cannot change another.

## Run it

```
python3 -m evaluation.run_all_exams
```

It prints one table (agent, what is measured, result, pass or fail) and writes `latest_scores.json`. The pass rule is the same as the one in each pack's tests:

| Agent | Pass when |
|---|---|
| `meeting_prep` | at least 85% of the topics that were asked before are covered, at least 55% of all decided topics, no failed runs, and the injection test is blocked |
| `project_risk` | every planted risk is found, no false alarms, at most 3 days late |
| `finance_watch` | every planted case is found, no false alarms |
| `fraud_watch` | every planted pattern is found, no false alarms |
| `hiring_forecast` | its team-by-team shortage and spare-capacity calls all agree with a check computed from the raw tables |

Any other pack with a `replay_exam.py` is picked up automatically (pass when nothing is missed and there are no false alarms).

The command exits with code 1 if any exam fails.

## Files in this folder

| File | What it does |
|---|---|
| `__init__.py` | Marks the folder as a Python package. |
| `run_all_exams.py` | Runs every pack's exam, prints the table and saves the scores. |
| `latest_scores.json` | The scores from the last run (written by `run_all_exams.py`). |
