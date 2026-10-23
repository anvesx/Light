"""A tiny clock for tests and demos. Time moves only when advance() is called."""
from datetime import datetime, timedelta


class FixedClock:
    def __init__(self, now: str = "2026-10-19T09:00"):
        self._now = datetime.fromisoformat(now)

    @property
    def now(self) -> str:
        return self._now.strftime("%Y-%m-%dT%H:%M")

    def advance(self, minutes: float) -> None:
        self._now += timedelta(minutes=minutes)
