# Hiring forecast agent

**Role in the harness:** Tells HR and the CEO each week which team will run short of people in the next 8 weeks, when to start hiring, and which team has spare hours.

**What it watches** (the code does the maths, the model only explains it):
- Each team's usable hours: people x 40 hours x 0.8 utilisation.
- Signed work: the hours left on each active project, spread evenly from today to the project's planned end date.
- New work: won deals that have not started (counted in full) and proposal-stage deals (counted at 50%). Deal value becomes hours at the average signed rate. The work is spread over 12 weeks from the expected start.
- A team is **short** in any week where the work coming is more than its usable hours. A team has **spare hours** when at least 15% of its usable hours are free on average.

**When it acts:** when HR, the CEO or the system timer asks (meant to run weekly). If no team is short and none has spare hours, the run ends quietly with no model call.

**Who it tells:** one private message each to HR and the CEO. For a short team it gives the first week of the shortfall, how many hours a week, about how many people, and a hiring start 4 weeks earlier. For a team with spare hours it says HR can hire less there.

**What it may never do:** show one person's hours, name a person, or mention pay. It reports teams only. A check before sending stops any text with a person id, a pay word, or a number that does not match the code's forecast. It never creates tasks and never contacts anyone outside DevX.

**Tools:** `team_capacity_and_load`, `pipeline_demand`, `remaining_sow_hours` (read); `send_private_message`.

**Assumptions** (stated again in every message):
- 40 hours a week per person, planned at 80%.
- Hiring takes about 4 weeks.
- Look ahead 8 weeks.
- Hours on one project go to teams in the share of that project's open task estimates. New work goes to teams in the share of the signed work.
- A deal that has already started is not counted twice: its hours are already in the signed projects.
- A project already past its SOW hours has nothing left in the forecast, even if tasks are open.

**How it is scored:** `replay_exam.py` builds an expected answer from the raw tables with a separate, simple calculation. It does not use the pack or the connector tools. This answer key is **derived, not planted**: no one wrote the expected answer into the dummy data. The exam runs the agent and checks that its short and spare teams agree with the key (hours within 1 hour, same start week and hiring date). Scores (`checked`, `agree`, `disagree`) are saved in company memory.

**HR situations it answers:**
- Which team runs short of people, given the won deals?
- When should we start hiring?
- Which team has spare hours, so we hire less there?

## Files in this folder

| File | What it does |
|---|---|
| `pack.py` | The agent: reads the three tools, works out the forecast, checks the model's text, messages HR and the CEO. |
| `fake_brain.py` | Stand-in for the model, for tests and demos. Writes the plain-English note from the forecast. |
| `replay_exam.py` | The exam. Derives the expected short and spare teams from the raw tables and compares them with the agent. |
| `README.md` | This page. |
