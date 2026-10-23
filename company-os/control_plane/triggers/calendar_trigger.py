"""Calendar trigger: one meeting_prep task per client meeting starting soon."""
import json

from contract.types import Task

COLUMNS = "event_id, title, start_at, attendees, client_id, project_id"


class CalendarTrigger:
    def __init__(self, data_conn):
        self.conn = data_conn
        self._seen = set()  # an event gives a task only once, even if due() runs every hour

    def due(self, clock, within_hours=24):
        rows = self.conn.execute(
            f"SELECT {COLUMNS} FROM calendar_events WHERE client_id IS NOT NULL"
            " AND start_at >= ? AND start_at <= ? ORDER BY start_at, event_id",
            (clock.now, clock.after_hours(within_hours))).fetchall()
        tasks = []
        for row in rows:
            event_id, title, start_at, attendees, client_id, project_id = tuple(row)
            if event_id in self._seen:
                continue
            self._seen.add(event_id)
            tasks.append(Task(
                agent="meeting_prep", caller_id="system", area_id=client_id, trigger_kind="event",
                prompt=f"Prepare for {title}",
                inputs={"event_id": event_id, "title": title, "start_at": start_at,
                        "project_id": project_id, "attendees": json.loads(attendees or "[]")}))
        return tasks
