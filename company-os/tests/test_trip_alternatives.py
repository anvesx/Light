"""trip_alternatives: real cheaper flights and hotels per trip, checked against separate queries on the raw tables."""
import json
import shutil
import tempfile
import unittest

from control_plane.connectors.spend_tools import make_trip_alternatives
from contract.types import RunContext, Task
from wiring.build_company_os import build_company_os

AS_OF = "2026-10-19"


class TripAlternativesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="alt_test_")
        cls.cos = build_company_os(agents=("spend_advisor",), state_dir=cls.dir)
        cls.tool = make_trip_alternatives(cls.cos.data_conn)
        ctx = RunContext("R1", Task("spend_advisor", "P01", "devx-internal", "request", inputs={"as_of": AS_OF}), None)
        cls.cards = {c["trip_id"]: c for c in json.loads(cls.tool.fn({"from": "2000-01-01"}, ctx))["trips"]}
        cls.ctx = ctx

    @classmethod
    def tearDownClass(cls):
        cls.cos.data_conn.close()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def one(self, sql, *a):
        return self.cos.data_conn.execute(sql, a).fetchone()

    def test_late_booking_trip_shows_three_real_cheaper_flights_cheapest_first(self):
        c = self.cards["TR015"]
        self.assertEqual(c["verdict"], "cheaper_option_existed")
        self.assertEqual(len(c["cheaper_flights"]), 3)
        fares = [f["fare_inr"] for f in c["cheaper_flights"]]
        self.assertEqual(fares, sorted(fares))
        booked = c["paid"]["booked_on"]
        for f in c["cheaper_flights"]:
            row = self.one("SELECT fare_inr, depart_time, arrive_time, seen_on, carrier FROM fare_options WHERE trip_id = 'TR015' "
                           "AND flight_no = ?", f["flight_no"])
            self.assertEqual((row[0], row[1], row[2], row[3], row[4]), (f["fare_inr"], f["depart_time"], f["arrive_time"],
                                                                         f["seen_on"], f["carrier"]))
            self.assertLessEqual(f["seen_on"], booked)
            self.assertEqual(f["saving_inr"], c["paid"]["fare_inr"] - f["fare_inr"])
            self.assertEqual(f["rule"], "late_booking")

    def test_business_short_flight_shows_economy_options_seen_on_the_booking_day(self):
        c = self.cards["TR008"]
        self.assertTrue(c["cheaper_flights"])
        for f in c["cheaper_flights"]:
            self.assertEqual((f["cabin"], f["seen_on"]), ("economy", c["paid"]["booked_on"]))

    def test_hotel_trip_shows_cheaper_hotels_with_nightly_saving(self):
        c = self.cards["TR012"]
        self.assertEqual(c["hotel_paid"]["hotel"], "Camp Stay")
        for h in c["cheaper_hotels"]:
            self.assertLess(h["rate_inr"], c["hotel_paid"]["rate_inr"])
            self.assertEqual(h["saving_inr"], (c["hotel_paid"]["rate_inr"] - h["rate_inr"]) * c["hotel_paid"]["nights"])
        self.assertEqual(c["rules"][0]["rule"], "hotel_above_city_rate")

    def test_every_cheaper_trip_has_an_option_and_best_trips_have_none(self):
        for c in self.cards.values():
            has = bool(c["cheaper_flights"] or c["cheaper_hotels"])
            self.assertEqual(has, c["verdict"] == "cheaper_option_existed", c["trip_id"])
            self.assertLessEqual((len(c["cheaper_flights"]), len(c["cheaper_hotels"])), (3, 3))

    def test_urgent_late_booking_gets_no_options(self):
        self.assertEqual(self.cards["TR006"]["cheaper_flights"], [])

    def test_no_traveller_name_anywhere(self):
        text = json.dumps(self.cards)
        for (name,) in self.cos.data_conn.execute("SELECT name FROM people"):
            self.assertNotIn(name, text)
        self.assertNotIn("person_id", text)

    def test_one_trip_by_id_and_unknown_trip(self):
        one = json.loads(self.tool.fn({"trip_id": "TR018"}, self.ctx))["trips"]
        self.assertEqual([t["trip_id"] for t in one], ["TR018"])
        self.assertEqual(json.loads(self.tool.fn({"trip_id": "TR999"}, self.ctx))["trips"], [])

    def test_bad_date_is_a_plain_error(self):
        self.assertIn("error", json.loads(self.tool.fn({"from": "yesterday"}, self.ctx)))

    def test_letter_shows_the_top_option(self):
        r = self.cos.run("spend_advisor", "P01", "devx-internal", inputs={"question": "Where can we save on travel?", "as_of": AS_OF})
        text = json.loads(r.final_text)["answer"]
        self.assertIn("A cheaper flight: Tarang Air TRG 341 at 5:15 PM, INR 7,320, seen Sep 8.", text)
        self.assertIn("A cheaper hotel: ", text)


if __name__ == "__main__":
    unittest.main()
