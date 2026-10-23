# triggers

**Role in the harness:** Triggers: what starts a run without anyone typing a prompt: a timer, a calendar event, or a person asking. Every trigger still passes the way-in check.

What starts a run. Each trigger gives `contract.types.Task` objects. Time comes only from the simulated clock.

## What is inside
- `simulated_clock.py`: `Clock(now="2026-10-19T09:00")` with `advance(minutes)`, `now`, `today`, `after_hours(h)`.
- `timer_trigger.py`: `TimerTrigger(schedule).due(clock)`. Rows are `{"agent", "area_id", "every": "daily"}`. One task per row per day, caller `system`.
- `request_trigger.py`: `parse_request(text, caller_id, event_area=None)`. "prep me for EV07" gives a `meeting_prep` task.
  Pass `event_area(event_id) -> area_id` to set the client area. Without it, or if it returns None, the area is `hold`.
- `calendar_trigger.py`: `CalendarTrigger(data_conn).due(clock, within_hours=24)`. Reads `calendar_events`. One task per client event, once only.
- `dispatch.py`: `dispatch(tasks, starter) -> list` calls `starter(task)` for each task.

## Use
```python
clock = Clock()
tasks = TimerTrigger([{"agent": "finance_watch", "area_id": "devx-internal", "every": "daily"}]).due(clock)
dispatch(tasks, runtime.run_task)  # the runtime runs the way-in check
```

## Files in this folder

| File | What it does |
|---|---|
| `calendar_trigger.py` | Calendar trigger: one meeting_prep task per client meeting starting soon. |
| `dispatch.py` | Dispatch: hands each task to a starter. The runtime behind the starter runs the way-in check. |
| `request_trigger.py` | Request trigger: turns a person's message such as "prep me for EV07" into a task. |
| `simulated_clock.py` | Simulated clock. All trigger logic reads time from here, never from the wall clock. |
| `timer_trigger.py` | Timer trigger: gives each schedule row one task per simulated day. |
