"""Tests for the simulated fare source: same inputs same options, counts, carriers, flight numbers, policy-rate hotels."""
import json
import unittest
from hashlib import sha1

from company_data.generate_trips import FLIGHT_CARRIERS, FLIGHT_HOURS, HOTELS, POLICY_RATE
from control_plane.connectors.fare_search import CARRIER_CODES, fare_tools, search_flights, search_hotels
from contract.types import RunContext, Task

DAY = "2026-10-28"


class FareSearchTests(unittest.TestCase):
    def test_same_inputs_give_the_same_options(self):
        self.assertEqual(search_flights("Mumbai", "Pune", DAY, 2), search_flights("Mumbai", "Pune", DAY, 2))
        self.assertEqual(search_hotels("Pune", DAY, 1, 1), search_hotels("Pune", DAY, 1, 1))
        self.assertNotEqual(search_flights("Mumbai", "Pune", DAY, 2), search_flights("Mumbai", "Pune", "2026-10-29", 2))

    def test_every_route_gives_8_to_12_flights_over_the_four_carriers(self):
        names = set()
        for (a, b) in FLIGHT_HOURS:
            flights = search_flights(a, b, DAY, 1)
            self.assertTrue(8 <= len(flights) <= 12, (a, b, len(flights)))
            names |= {f["carrier"] for f in flights}
            self.assertEqual([f["depart_time"] for f in flights], sorted(f["depart_time"] for f in flights))
        self.assertEqual(names, set(FLIGHT_CARRIERS))

    def test_flight_option_shape_and_number_format(self):
        for f in search_flights("Delhi", "Mumbai", DAY, 1):
            self.assertTrue({"option_id", "carrier", "flight_no", "depart_time", "arrive_time", "cabin", "stops",
                             "fare_inr", "seats_left"} <= set(f))
            code, number = f["flight_no"].split()
            self.assertEqual(code, CARRIER_CODES[f["carrier"]])
            self.assertTrue(100 <= int(number) <= 999)
            key = f"{code}|Delhi|Mumbai|{DAY}|{f['depart_time']}"
            self.assertEqual(int(number), 100 + int(sha1(key.encode()).hexdigest(), 16) % 900)
            self.assertEqual(f["cabin"], "economy")
            self.assertGreater(f["fare_inr"], 0)

    def test_business_costs_more_and_routes_work_both_ways(self):
        eco = {f["depart_time"]: f for f in search_flights("Mumbai", "Pune", DAY, 1)}
        biz = {f["depart_time"]: f for f in search_flights("Mumbai", "Pune", DAY, 1, "business")}
        self.assertEqual(set(eco), set(biz))
        self.assertTrue(all(biz[t]["fare_inr"] > eco[t]["fare_inr"] for t in eco))
        self.assertTrue(search_flights("Pune", "Mumbai", DAY, 1))

    def test_bad_input_is_an_error(self):
        with self.assertRaises(ValueError):
            search_flights("Mumbai", "Goa", DAY, 1)
        with self.assertRaises(ValueError):
            search_flights("Mumbai", "Pune", DAY, 1, "first")
        with self.assertRaises(ValueError):
            search_hotels("Goa", DAY, 1, 1)

    def test_hotels_come_from_the_city_list_with_at_least_three_in_policy(self):
        for city in HOTELS:
            hotels = search_hotels(city, DAY, 2, 1)
            self.assertEqual({h["hotel"] for h in hotels}, set(HOTELS[city]))
            self.assertGreaterEqual(sum(h["rate_inr"] <= POLICY_RATE[city] for h in hotels), 3)
            for h in hotels:
                self.assertTrue(3 <= h["stars"] <= 5 and h["km_to_center"] > 0 and h["city"] == city)

    def test_tools_reply_with_json_and_reject_bad_arguments(self):
        flights, hotels = fare_tools()
        ctx = RunContext("R1", Task("travel_booking", "P01", "devx-internal", "request"), None)
        ok = json.loads(flights.fn({"from_city": "Mumbai", "to_city": "Pune", "date": DAY, "pax": 2}, ctx))
        self.assertTrue(8 <= len(ok["flights"]) <= 12)
        self.assertIn("error", json.loads(flights.fn({"from_city": "Mumbai", "to_city": "Goa", "date": DAY}, ctx)))
        self.assertIn("error", json.loads(flights.fn({"from_city": "Mumbai", "to_city": "Pune", "date": "tomorrow"}, ctx)))
        self.assertEqual(len(json.loads(hotels.fn({"city": "Pune", "check_in": DAY, "nights": 1, "rooms": 1}, ctx))["hotels"]), 4)
        other = RunContext("R2", Task("travel_booking", "P01", "C01", "request"), None)
        self.assertIn("error", json.loads(flights.fn({"from_city": "Mumbai", "to_city": "Pune", "date": DAY}, other)))


if __name__ == "__main__":
    unittest.main()
