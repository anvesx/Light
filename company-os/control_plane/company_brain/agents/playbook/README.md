# playbook

**Role in the harness:** Brain agent 4. It turns a won or lost deal into a redacted playbook and kickoff checklist questions in the library area `playbooks`.

- Run: caller `system`, trigger `event`, area of the deal's client, inputs `{"deal_id"}`.
- Code builds the five sections (`control_plane/company_brain/playbook_rules.py`) and redacts names, emails and phone numbers (`control_plane/company_brain/redaction.py`).
- The check step refuses on any leak or any entry that does not cite items of its own area. Nothing is saved then.
- `fake_brain.leaky_brain` is for the refusal test only.
- Exam: `replay_exam.py` writes the four answer-key playbooks and checks required topics, own-area evidence, 0 leaks and that a leaky draft is refused.
