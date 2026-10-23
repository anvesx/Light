"""Tests for triggers: clock, timer, request, calendar, dispatch."""
import json
import sqlite3
import unittest

from contract.types import Task
from control_plane.triggers import CalendarTrigger, Clock, TimerTrigger, dispatch, parse_request


class TestClock(unittest.TestCase):
    def test_default_and_advance(self):
        clock = Clock()
        self.assertEqual((clock.now, clock.today), ("2026-10-19T09:00", "2026-10-19"))
        clock.advance(90)
        self.assertEqual(clock.now, "2026-10-19T10:30")
        clock.advance(24 * 60)
        self.assertEqual((clock.now, clock.today), ("2026-10-20T10:30", "2026-10-20"))


class TestTimer(unittest.TestCase):
    def test_once_per_day_per_row(self):
        timer = TimerTrigger([{"agent": "finance_watch", "area_id": "devx-internal", "every": "daily"},
                              {"agent": "finance_watch", "area_id": "C01", "every": "daily"}])
        clock = Clock()
        tasks = timer.due(clock)
        self.assertEqual([(t.agent, t.area_id, t.caller_id, t.trigger_kind) for t in tasks],
                         [("finance_watch", "devx-internal", "system", "timer"),
                          ("finance_watch", "C01", "system", "timer")])
        self.assertTrue(all(isinstance(t, Task) for t in tasks))
        clock.advance(60)
        self.assertEqual(timer.due(clock), [])
        clock.advance(24 * 60)
        self.assertEqual(len(timer.due(clock)), 2)

    def test_unknown_schedule_rejected(self):
        with self.assertRaises(ValueError):
            TimerTrigger([{"agent": "a", "area_id": "C01", "every": "hourly"}])


class TestRequest(unittest.TestCase):
    def test_prep_request(self):
        task = parse_request("prep me for EV07", "P05", event_area=lambda e: {"EV07": "C03"}.get(e))
        self.assertEqual((task.agent, task.caller_id, task.area_id, task.trigger_kind), ("meeting_prep", "P05", "C03", "request"))
        self.assertEqual(task.inputs["event_id"], "EV07")

    def test_without_lookup_area_is_hold(self):
        task = parse_request("Prep me for ev07 please", "P05")
        self.assertEqual((task.area_id, task.inputs["event_id"]), ("hold", "EV07"))
        self.assertEqual(parse_request("prep for EV99", "P05", event_area=lambda e: None).area_id, "hold")

    def test_other_text_gives_none(self):
        self.assertIsNone(parse_request("what is the weather", "P05"))
        self.assertIsNone(parse_request("prep me for lunch", "P05"))


class TestCalendar(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.addCleanup(self.conn.close)
        self.conn.execute("CREATE TABLE calendar_events (event_id TEXT PRIMARY KEY, title TEXT, start_at TEXT,"
                          " attendees TEXT, client_id TEXT, project_id TEXT, meeting_id TEXT)")
        rows = [("EV01", "Acme sync", "2026-10-19T15:00", json.dumps(["P05", "X01"]), "C01", "PR01", None),
                ("EV02", "Beta review", "2026-10-20T08:00", "[]", "C02", "PR02", None),
                ("EV03", "Internal standup", "2026-10-19T10:00", "[]", None, None, None),
                ("EV04", "Later sync", "2026-10-22T10:00", "[]", "C01", "PR01", None),
                ("EV05", "Already past", "2026-10-19T08:00", "[]", "C01", "PR01", None)]
        self.conn.executemany("INSERT INTO calendar_events VALUES (?, ?, ?, ?, ?, ?, ?)", rows)

    def test_one_task_per_client_event_in_next_24_hours(self):
        tasks = CalendarTrigger(self.conn).due(Clock())
        self.assertEqual([t.inputs["event_id"] for t in tasks], ["EV01", "EV02"])
        first = tasks[0]
        self.assertEqual((first.agent, first.area_id, first.trigger_kind), ("meeting_prep", "C01", "event"))
        self.assertEqual(first.inputs["attendees"], ["P05", "X01"])
        self.assertEqual(first.inputs["project_id"], "PR01")

    def test_window_moves_with_clock_and_no_repeats(self):
        trigger, clock = CalendarTrigger(self.conn), Clock()
        trigger.due(clock)
        self.assertEqual(trigger.due(clock), [])
        clock.advance(2 * 24 * 60 + 120)
        self.assertEqual([t.inputs["event_id"] for t in trigger.due(clock)], ["EV04"])

    def test_within_hours(self):
        self.assertEqual([t.inputs["event_id"] for t in CalendarTrigger(self.conn).due(Clock(), within_hours=5)], [])
        self.assertEqual([t.inputs["event_id"] for t in CalendarTrigger(self.conn).due(Clock(), within_hours=80)],
                         ["EV01", "EV02", "EV04"])

    def test_works_with_row_factory(self):
        self.conn.row_factory = sqlite3.Row
        self.assertEqual(len(CalendarTrigger(self.conn).due(Clock())), 2)


class TestDispatch(unittest.TestCase):
    def test_starter_called_for_each_task_in_order(self):
        tasks = [Task("a", "system", "C01", "timer"), Task("b", "system", "C02", "timer")]
        seen = []
        results = dispatch(tasks, lambda t: seen.append(t.agent) or t.area_id)
        self.assertEqual(seen, ["a", "b"])
        self.assertEqual(results, ["C01", "C02"])
        self.assertEqual(dispatch([], lambda t: 1), [])


if __name__ == "__main__":
    unittest.main()
