# people_surface

**Role in the harness:** The people surface: where agents reach people. Private messages (Slack in production) and the approval queue for risky actions.

Where agents reach people. Both parts keep their rows in `people_surface.db` by default.

## What is inside
- `private_outbox.py`: `Outbox`. Stands in for private Slack messages.
  - `post(to_person_id, text, *, run_id, agent, kind) -> msg_id`
  - `messages(to_person_id=None) -> list[dict]`
- `approval_queue.py`: `Approvals`. Risky tool calls wait here for a person.
  - `request(run_id, agent, tool, args, reason) -> approval_id`
  - `pending()` lists the requests with no decision.
  - `decide(approval_id, approved, by_person_id)`: status becomes `approved` or `rejected`. A second decision raises `ValueError`.

## Use
```python
from people_surface import Outbox, Approvals
box = Outbox("/tmp/ps.db")
box.post("P05", "Brief for EV07", run_id="R000001", agent="meeting_prep", kind="brief")
queue = Approvals("/tmp/ps.db")
a = queue.request("R000001", "fraud_watch", "send_message", {"to": "P20"}, "reaches a person")
queue.decide(a, True, "P01")
```
Both classes take an optional `clock` (any object with `.now`) that stamps the rows.

## Files in this folder

| File | What it does |
|---|---|
| `_sqlite_open.py` | Open a SQLite file for the people surface, making its folder if needed. |
| `approval_queue.py` | Approval queue: risky tool calls wait here until a person decides. |
| `private_outbox.py` | Private message outbox. Stands in for private Slack messages to DevX people. |
