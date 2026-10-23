"""Tests for the trip data: rows, links, repeatability, old tables unchanged, planted spend cases and look-alikes."""
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import unittest

from company_data.generate_dummy_data import build
from company_data.generate_trips import (POLICY_RATE, SPEND_RULES, business_short, hotel_over_policy, late_booking,
                                         same_city_pairs)
from company_data.simulated_today import TODAY

NEW = ["trips", "hotel_stays", "fare_options", "hotel_options", "city_hotel_rates"]


def table_hash(conn, t):
    h = hashlib.sha256()
    for r in conn.execute(f"SELECT * FROM {t} ORDER BY rowid"):
        h.update(repr(tuple(r)).encode())
    return h.hexdigest()


def make(tmp, name, **kw):
    d = os.path.join(tmp, name)
    os.makedirs(d)
    path = build(os.path.join(d, "c.db"), **kw)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn, os.path.join(d, "answer_keys.json")


class TripsDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.conn, cls.keys_path = make(cls.tmp, "a")
        cls.keys = json.load(open(cls.keys_path))["spend_advisor"]

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        shutil.rmtree(cls.tmp)

    def q(self, sql, *a):
        return [dict(r) for r in self.conn.execute(sql, a).fetchall()]

    def test_new_tables_have_rows_and_valid_links(self):
        for t in NEW:
            self.assertGreater(self.q(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"], 0, t)
        self.assertEqual(self.q("PRAGMA foreign_key_check"), [])
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM trips WHERE depart_on < '2026-04-01' OR return_on > ?",
                                TODAY)[0]["n"], 0)

    def test_trips_add_up_to_the_existing_travel_expenses(self):
        rows = self.q("SELECT e.expense_id, e.amount_inr, e.category, "
                      "(SELECT SUM(fare_inr) FROM trips t WHERE t.expense_id = e.expense_id) AS fares, "
                      "(SELECT COALESCE(SUM(h.total_inr), 0) FROM hotel_stays h JOIN trips t USING(trip_id) "
                      " WHERE t.expense_id = e.expense_id) AS hotels FROM expenses e WHERE e.expense_id IN "
                      "(SELECT expense_id FROM trips)")
        self.assertGreater(len(rows), 10)
        for r in rows:
            self.assertEqual(r["category"], "travel")
            self.assertEqual(r["fares"] + r["hotels"], r["amount_inr"], r["expense_id"])

    def test_story_is_mostly_growth_and_csms_in_indian_cities(self):
        teams = [r["team"] for r in self.q("SELECT team FROM trips")]
        self.assertGreater(sum(t in ("growth", "customer_success") for t in teams) / len(teams), 0.6)
        cities = {r["to_city"] for r in self.q("SELECT to_city FROM trips")} | {r["from_city"] for r in self.q("SELECT from_city FROM trips")}
        self.assertTrue(cities <= set(POLICY_RATE), cities)
        self.assertEqual({r["city"] for r in self.q("SELECT city FROM city_hotel_rates")}, set(POLICY_RATE))
        self.assertEqual({r["purpose"] for r in self.q("SELECT purpose FROM trips")}, {"client meeting", "internal", "event"})

    def test_same_seed_same_rows(self):
        conn2, keys2 = make(self.tmp, "b")
        for t in NEW:
            self.assertEqual(table_hash(self.conn, t), table_hash(conn2, t), t)
        self.assertEqual(json.load(open(keys2))["spend_advisor"], self.keys)
        conn2.close()

    def test_existing_tables_unchanged(self):
        conn0, keys0 = make(self.tmp, "c", spend_trips=False)
        for t in NEW:
            self.assertEqual(conn0.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0], 0)
        tables = [r[0] for r in conn0.execute("SELECT name FROM sqlite_master WHERE type='table'") if r[0] not in NEW]
        self.assertGreater(len(tables), 30)
        for t in tables:
            self.assertEqual(table_hash(self.conn, t), table_hash(conn0, t), t)
        old, new = json.load(open(keys0)), json.load(open(self.keys_path))
        self.assertEqual({k: v for k, v in new.items() if k != "spend_advisor"}, old)
        conn0.close()

    def rules_found(self):
        trips = self.q("SELECT * FROM trips")
        out = []
        for t in trips:
            opts = self.q("SELECT * FROM fare_options WHERE trip_id = ?", t["trip_id"])
            out += [x for x in (late_booking(t, opts), business_short(t, opts)) if x]
        out += same_city_pairs(trips)
        for s in self.q("SELECT * FROM hotel_stays"):
            alts = self.q("SELECT * FROM hotel_options WHERE stay_id = ? AND hotel != ?", s["stay_id"], s["hotel"])
            dep = self.q("SELECT depart_on FROM trips WHERE trip_id = ?", s["trip_id"])[0]["depart_on"]
            x = hotel_over_policy(s, POLICY_RATE[s["city"]], alts, dep)
            if x:
                out.append(x)
        return out

    def test_the_rules_find_exactly_the_planted_cases(self):
        found = self.rules_found()
        self.assertEqual(len(self.keys["cases"]), 9)
        self.assertEqual(sorted((x["rule"], x["trip_id"]) for x in found),
                         sorted((c["signal"], c["trip_ids"][0]) for c in self.keys["cases"]))
        by_rule = {}
        for c in self.keys["cases"]:
            by_rule[c["signal"]] = by_rule.get(c["signal"], 0) + 1
        self.assertEqual(by_rule, dict(late_booking=3, business_short_flight=2, same_city_trips=2, hotel_above_city_rate=2))
        for c in self.keys["cases"]:
            x = next(f for f in found if f["rule"] == c["signal"] and f["trip_id"] == c["trip_ids"][0])
            self.assertEqual(x["saving_inr"], c["saving_inr"])
            self.assertGreater(c["saving_inr"], 0)

    def test_late_booking_has_a_much_cheaper_fare_a_week_or_two_before(self):
        for c in [c for c in self.keys["cases"] if c["signal"] == "late_booking"]:
            t = self.q("SELECT * FROM trips WHERE trip_id = ?", c["trip_ids"][0])[0]
            self.assertLessEqual(self.q("SELECT julianday(?) - julianday(?) AS d", t["depart_on"], t["booked_on"])[0]["d"], 3)
            self.assertGreaterEqual(c["saving_inr"], SPEND_RULES["min_saving_share"] * t["fare_inr"])

    def test_look_alikes_are_not_flagged(self):
        flagged = {(x["rule"], x["trip_id"]) for x in self.rules_found()}
        ids = {i for la in self.keys["look_alikes"] for i in la["trip_ids"]}
        self.assertEqual(len(ids), 2)
        self.assertFalse({t for _, t in flagged} & ids)
        urgent = self.q("SELECT * FROM trips WHERE trip_id = ?", self.keys["look_alikes"][0]["trip_ids"][0])[0]
        self.assertIn("urgent", urgent["note"].lower())
        self.assertLessEqual(self.q("SELECT julianday(?) - julianday(?) AS d", urgent["depart_on"], urgent["booked_on"])[0]["d"], 3)
        cheap = self.q("SELECT * FROM trips WHERE trip_id = ?", self.keys["look_alikes"][1]["trip_ids"][0])[0]
        self.assertEqual(cheap["cabin"], "business")
        econ = self.q("SELECT MIN(fare_inr) AS m FROM fare_options WHERE trip_id = ? AND cabin = 'economy' AND seen_on = ?",
                      cheap["trip_id"], cheap["booked_on"])[0]["m"]
        self.assertGreater(econ, cheap["fare_inr"])

    def test_later_bookings_cost_more(self):
        late = self.q("SELECT trip_id, fare_inr FROM trips WHERE trip_id = ?", self.keys["cases"][2]["trip_ids"][0])[0]
        cheapest = self.q("SELECT MIN(fare_inr) AS m FROM fare_options WHERE trip_id = ? AND cabin = 'economy'", late["trip_id"])[0]["m"]
        self.assertLess(cheapest, late["fare_inr"])


if __name__ == "__main__":
    unittest.main()
