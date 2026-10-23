# Deal brief agent

Prepares Growth for a live deal, for example C07 CareNest. Started by growth, ceo or rnd_lead. It reads the library (`reads_library = True`).

**It gives.** Similar past clients (from redacted playbooks only), ideas to close tied to a lesson, risks, and a kickoff checklist of questions that past clients raised late.

**Rules.** Every point cites a playbook id (`PB-...`) or an item of this deal's own area. Items the brain is unsure of are labelled "Unconfirmed". The check step blocks unknown cites, other clients' items, contact names and emails. It never reads another client's raw items, finance or project data.

**Tools.** `deal_overview` (own area), `similar_playbooks` and `kickoff_checklist` (library), in `control_plane/connectors/deal_brain_tools.py`. Code picks the similar deals and the checklist; the model writes the ideas and questions.

Files: `pack.py`, `fake_brain.py`, `replay_exam.py` (with `judge`), `exam_fixture.py` (stand-in library built from the answer keys, used only when the brain has no playbooks).
Run the exam: `python3 -m agents.meeting_prep.deal_brief.replay_exam`.
