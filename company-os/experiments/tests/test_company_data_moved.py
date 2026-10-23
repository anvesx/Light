"""Tests for company_data: rows exist, builds are repeatable, and every planted case can be seen in the data."""
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta

from company_data import connect, DB_PATH
from company_data.generate_dummy_data import build
from company_data.planted_cases import INJECTION_INSTRUCTION
from company_data.simulated_today import TODAY

# Tables the git and client request generators fill. They are off by default, so they stay empty.
EMPTY_BY_DEFAULT = {"repos", "scope_items", "task_scope", "pull_requests", "deploys", "project_profiles", "client_requests",
                    "client_request_events", "access_checks", "task_blocks"}
TABLES = ["clients", "people", "leads", "growth_calls", "sows", "sow_changes", "projects", "tasks", "time_logs",
          "meetings", "meeting_items", "calendar_events", "slack_messages", "vendors", "invoices", "payments",
          "expenses", "budgets", "stores", "pos_orders", "pos_refunds", "pos_discounts", "alterations",
    "repos", "scope_items", "task_scope", "pull_requests", "deploys",
    "project_profiles", "client_requests", "client_request_events", "access_checks", "task_blocks",
    "trips", "hotel_stays", "fare_options", "hotel_options", "city_hotel_rates",
]


def D(s):
    return date.fromisoformat(s)


def minus(s, n=1):
    return (D(s) - timedelta(days=n)).isoformat()


class CompanyDataTest(unittest.TestCase):
    def test_over_sow_project(self):
        c = self.case("project_risk", "RISK-1")
        pid, first = c["project_id"], c["first_detectable_on"]
        self.assertGreater(self.logged(pid, TODAY) / self.sow_hours(pid, TODAY), 1.15)
        self.assertGreaterEqual(self.open_share(pid, TODAY), 0.30)
        self.assertTrue(self.over_sow(pid, first))
        self.assertFalse(self.over_sow(pid, minus(first)))
        self.assertLess(first, TODAY)
        others = [r[0] for r in self.q("SELECT project_id FROM projects WHERE project_id<>?", pid)]
        for other in others:
            for d in self.days(self.one("SELECT start_on FROM projects WHERE project_id=?", other))[::3]:
                self.assertFalse(self.over_sow(other, d), (other, d))

    def test_quiet_client(self):
        c = self.case("project_risk", "RISK-2")
        pid, first = c["project_id"], c["first_detectable_on"]
        self.assertEqual(self.one("SELECT status FROM projects WHERE project_id=?", pid), "active")
        self.assertGreaterEqual(self.days_since_client_message(pid, first), 14)
        self.assertLess(self.days_since_client_message(pid, minus(first)), 14)
        active = [r[0] for r in self.q("SELECT project_id FROM projects WHERE status='active' AND project_id<>?", pid)]
        for other in active:
            start = self.one("SELECT start_on FROM projects WHERE project_id=?", other)
            for d in self.days(start, TODAY)[::2]:
                self.assertLess(self.days_since_client_message(other, d), 14, (other, d))

    def test_overloaded_engineer(self):
        c = self.case("project_risk", "RISK-3")
        p, sunday = c["person_id"], c["first_detectable_on"]
        self.assertEqual(D(sunday).weekday(), 6)
        for i in range(3):
            end = minus(sunday, 7 * i)
            hours = self.one("SELECT SUM(hours) FROM time_logs WHERE person_id=? AND date>? AND date<=?",
                             p, minus(end, 7), end)
            self.assertGreater(hours, 55)
        prior = self.one("SELECT SUM(hours) FROM time_logs WHERE person_id=? AND date>? AND date<=?",
                         p, minus(sunday, 28), minus(sunday, 21))
        self.assertLessEqual(prior, 55)
        weeks = self.q("SELECT person_id, strftime('%Y-%W', date) w, SUM(hours) h FROM time_logs GROUP BY 1, 2")
        over = {r["person_id"] for r in weeks if r["h"] > 55}
        self.assertEqual(over, {p})

    def test_overdue_project(self):
        c = self.case("project_risk", "RISK-4")
        pid, first = c["project_id"], c["first_detectable_on"]
        self.assertGreaterEqual(self.overdue(pid, first), 5)
        self.assertLess(self.overdue(pid, minus(first)), 5)
        self.assertGreaterEqual(self.overdue(pid, TODAY), 5)
        for other in [r[0] for r in self.q("SELECT project_id FROM projects WHERE status='active' AND project_id<>?", pid)]:
            start = self.one("SELECT start_on FROM projects WHERE project_id=?", other)
            for d in self.days(start)[::2]:
                self.assertLess(self.overdue(other, d), 5, (other, d))

    def test_project_risk_look_alikes(self):
        a = self.case("project_risk", "RISK-L1", "look_alikes")["project_id"]
        self.assertGreater(self.logged(a, TODAY), 1.15 * self.sow_hours(a, TODAY, with_changes=False))
        self.assertLessEqual(self.logged(a, TODAY), 1.15 * self.sow_hours(a, TODAY))
        self.assertGreater(self.one("SELECT COUNT(*) FROM projects p JOIN sow_changes c USING(sow_id) "
                                    "WHERE p.project_id=? AND c.accepted=1", a), 0)
        b = self.case("project_risk", "RISK-L2", "look_alikes")["project_id"]
        self.assertEqual(self.one("SELECT status FROM projects WHERE project_id=?", b), "paused")
        self.assertGreaterEqual(self.days_since_client_message(b, TODAY), 14)

    def test_cash_refunds(self):
        c = self.case("fraud_watch", "FRD-1")
        sql = "SELECT COUNT(*) FROM pos_refunds WHERE method='cash' AND staff_id=?"
        self.assertGreaterEqual(self.window_count(sql, c["person_id"], c["first_detectable_on"]), 5)
        self.assertLess(self.window_count(sql, c["person_id"], minus(c["first_detectable_on"])), 5)
        worst = self.q("SELECT staff_id, COUNT(*) n FROM pos_refunds WHERE method='cash' GROUP BY 1 ORDER BY n DESC")
        self.assertEqual(worst[0]["staff_id"], c["person_id"])
        for other in self.q("SELECT DISTINCT staff_id FROM pos_refunds WHERE method='cash' AND staff_id<>?", c["person_id"]):
            for r in self.q("SELECT date FROM pos_refunds WHERE method='cash' AND staff_id=?", other[0]):
                self.assertLess(self.window_count(sql, other[0], r["date"]), 5)

    def test_self_approved_discounts(self):
        c = self.case("fraud_watch", "FRD-2")
        rows = self.q("SELECT requester_id, MIN(date) d, COUNT(*) n FROM pos_discounts WHERE requester_id=approver_id GROUP BY 1")
        self.assertEqual([(r["requester_id"], r["d"], r["n"]) for r in rows],
                         [(c["person_id"], c["first_detectable_on"], c["count"])])
        self.assertGreaterEqual(c["count"], 5)

    def test_free_remakes(self):
        c = self.case("fraud_watch", "FRD-3")
        sql = "SELECT COUNT(*) FROM alterations WHERE kind='remake' AND charged=0 AND staff_id=?"
        self.assertGreaterEqual(self.window_count(sql, c["person_id"], c["first_detectable_on"]), 5)
        self.assertLess(self.window_count(sql, c["person_id"], minus(c["first_detectable_on"])), 5)
        for r in self.q("SELECT staff_id, date FROM alterations WHERE kind='remake' AND charged=0 AND staff_id<>?",
                        c["person_id"]):
            self.assertLess(self.window_count(sql, r["staff_id"], r["date"]), 5)

    def test_fraud_look_alikes(self):
        a = self.case("fraud_watch", "FRD-L1", "look_alikes")
        rows = self.q("SELECT store_id, method, COUNT(DISTINCT staff_id) s, COUNT(*) n FROM pos_refunds "
                      "WHERE reason='recall' GROUP BY 1, 2")
        self.assertEqual([(r["store_id"], r["method"]) for r in rows], [(a["store_id"], "card")])
        self.assertGreaterEqual(rows[0]["n"], 15)
        self.assertGreaterEqual(rows[0]["s"], 3)
        b = self.case("fraud_watch", "FRD-L2", "look_alikes")
        n = self.one("SELECT COUNT(*) FROM pos_discounts WHERE approver_id=? AND requester_id<>approver_id "
                     "AND date BETWEEN '2026-08-10' AND '2026-08-16'", b["person_id"])
        self.assertGreaterEqual(n, 20)
        manager = self.one("SELECT manager_id FROM stores WHERE store_id=?", b["store_id"])
        self.assertEqual(manager, b["person_id"])


class FullTableRows(CompanyDataTest):
    """The original row-count check: with the git and client request generators on, every table has rows."""
    def test_every_table_has_rows(self):
        names = {r[0] for r in self.q("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(names, set(TABLES))
        for t in TABLES:
            self.assertGreater(self.one(f"SELECT COUNT(*) FROM {t}"), 0, t)
