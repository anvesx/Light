# live_copilot

**Role in the harness:** While a call plays, it suggests the next question from the brain. It is the third mode of the meeting prep agent.

## Files
- `listener.py`: `LiveListener.hear(line)`, plain code, no model. Finds a gap, a contradiction or an unasked kickoff item.
- `live_session.py`: `LiveSession`, one guarded run per call. Reads go through `invoke_tool`. `end()` makes the one model call (the summary) and stores the call as a `live_call` source.
- `pack.py`, `fake_brain.py`: the pack (tools `live_call_script`, `live_call_brain`) and the fake summary writer. A one-shot run replays the whole call.
- `call_brain_seed.py`: fills a brain from the F1 answer keys (history sources, kickoff checklist), for tests and the exam.
- `replay_exam.py`: plays LC01 and LC02. Pass: recall 0.9, at most 1 false suggestion per call, LC02 contradiction found, p95 per line under 200 ms.

## Rules
- At most one suggestion per line and per topic per call.
- CSM calls read the project area only. Growth calls also read the library.
- Client text is data, never orders.
