"""Simulated clock. All trigger logic reads time from here, never from the wall clock."""
from datetime import datetime, timedelta

FORMAT = "%Y-%m-%dT%H:%M"


class Clock:
    def __init__(self, now="2026-10-19T09:00"):
        self._dt = datetime.fromisoformat(now)

    def advance(self, minutes):
        self._dt += timedelta(minutes=minutes)
        return self.now

    @property
    def now(self):
        return self._dt.strftime(FORMAT)

    @property
    def today(self):
        return self._dt.strftime("%Y-%m-%d")

    def after_hours(self, hours):
        """The time string `hours` from now."""
        return (self._dt + timedelta(hours=hours)).strftime(FORMAT)
