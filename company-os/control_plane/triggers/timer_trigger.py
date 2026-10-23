"""Timer trigger: gives each schedule row one task per simulated day."""
from contract.types import Task

SUPPORTED = ("daily",)


class TimerTrigger:
    def __init__(self, schedule):
        """schedule rows: {"agent", "area_id", "every": "daily"}."""
        for row in schedule:
            if row.get("every", "daily") not in SUPPORTED:
                raise ValueError(f"unsupported schedule: {row.get('every')!r}")
        self.schedule = list(schedule)
        self._fired = set()

    def due(self, clock):
        tasks = []
        for index, row in enumerate(self.schedule):
            key = (index, clock.today)
            if key in self._fired:
                continue
            self._fired.add(key)
            tasks.append(Task(agent=row["agent"], caller_id="system", area_id=row["area_id"],
                              trigger_kind="timer", prompt=f"Scheduled {row.get('every', 'daily')} run",
                              inputs={"date": clock.today}))
        return tasks
