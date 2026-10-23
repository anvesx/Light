# Project risk agent

Looks for trouble on a client's projects early, and tells the project's CSM in a private message.
CSMs are DevX's project managers. They manage projects and the people on them.

**What it watches** (the code finds these, the model only explains them):
- Hours logged are more than 115% of the SOW estimate (accepted SOW changes count in the estimate) while 30% or more of the tasks are open.
- A client has written nothing in the shared Slack channel for 14 days or more on an active project. A paused project is never "silent".
- 5 or more open tasks are past their due date.
- One person logged more than 55 hours a week for 3 weeks in a row. This is only a flag.
- Optional: a SOW change the client has not accepted adds more hours than are left.

**When it acts:** every day on a timer, for each client. A CSM, project lead, CEO or CTO can also ask for a run.
If nothing is wrong, the run ends quietly with no model call.

**Who it tells:** one private message per CSM, with the evidence in numbers, why it matters and a suggested next step.
A flag that names one person goes only to that project's CSM.

**What it may never do:** message anyone outside DevX, read another client's data, build a people or bandwidth report,
or create a task on its own. For high-severity flags it may propose a follow-up task. That task waits until a CSM or the CEO approves it.
Before anything is sent, a check confirms that every number and id in a flag matches what the code found.

**Bandwidth stays in DevX's existing console** (console.devxlabs.ai/employees). This agent does not rebuild it.
In production it would read bandwidth from that console through a connector.

**Tools:** `project_overview`, `project_tasks`, `weekly_hours_by_person`, `client_channel_activity` (read);
`send_private_message`; `create_followup_task` (risky, held for approval).

**How it is scored:** `replay_exam.py` replays each client day by day from 2026-09-01 to today and compares with the planted cases:
found or missed, days late against the first day a case could be seen, and false alarms on look-alikes
(a project over hours with an accepted SOW change, a quiet client on a paused project).
Scores are saved in company memory.

**Files:** `pack.py` (the agent), `fake_brain.py` (stand-in for the model, for tests and demos), `replay_exam.py`.
