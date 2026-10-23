"""Tests for the travel booking agent: parser, policy ranking, the held approval, booking once, role views, the exam."""
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from agents.finance.travel_booking import replay_exam, service
from agents.finance.travel_booking.policy_ranking import rank_flights, rank_hotels
from agents.finance.travel_booking.request_parser import RequestError, parse_request
from company_data.generate_trips import POLICY_RATE
from control_plane.connectors.fare_search import search_flights, search_hotels
from evaluation.run_all_exams import close_all
from wiring.build_company_os import build_company_os

TEXT = "flights for 3 people Mumbai to Pune on 2026-10-28, back on 2026-10-29"
POLICY = json.loads((Path(replay_exam.__file__).parent / "travel_policy.json").read_text())


class ParserTests(unittest.TestCase):
    def test_text_with_iso_dates(self):
        self.assertEqual(parse_request(TEXT), {"from_city": "Mumbai", "to_city": "Pune", "pax": 3, "depart_on": "2026-10-28",
                                               "return_on": "2026-10-29", "purpose": "business trip"})

    def test_month_names_words_aliases_and_client(self):
        r = parse_request("book flights for four travellers from Bangalore to Delhi on 3rd Nov, returning Nov 5 for client C07")
        self.assertEqual((r["from_city"], r["pax"], r["depart_on"], r["return_on"], r["client_id"]),
                         ("Bengaluru", 4, "2026-11-03", "2026-11-05", "C07"))

    def test_nights_make_a_return_date(self):
        self.assertEqual(parse_request("2 people Mumbai to Pune on 2026-10-28 for 2 nights")["return_on"], "2026-10-30")

    def test_bad_requests_give_plain_errors(self):
        for text in ("hello", "2 people Mumbai to Goa on 2026-10-28", "Mumbai to Pune on 2026-10-28",
                     "2 people Mumbai to Pune", "2 people Mumbai to Pune on 2026-10-01", "0 people Mumbai to Pune on 2026-10-28",
                     "2 people Mumbai to Pune on 2026-10-28, back on 2026-10-27", "", "2 people Pune to Pune on 2026-10-28"):
            with self.assertRaises(RequestError, msg=text):
                parse_request(text)

    def test_dict_request_is_checked_too(self):
        with self.assertRaises(RequestError):
            parse_request("12 people Mumbai to Pune on 2026-10-28")


class RankingTests(unittest.TestCase):
    def test_flights_follow_the_policy_then_price(self):
        req = {"from_city": "Bengaluru", "to_city": "Delhi", "pax": 2}
        options = search_flights("Bengaluru", "Delhi", "2026-11-09", 2) + search_flights("Bengaluru", "Delhi", "2026-11-09", 2, "business")
        top, bad = rank_flights(options, req)
        self.assertEqual(len(top), 3)
        self.assertEqual([f["fare_inr"] for f in top], sorted(f["fare_inr"] for f in top))
        w = POLICY["depart_window"]
        for f in top:
            self.assertTrue(w["from"] <= f["depart_time"] <= w["to"])
            self.assertTrue(f["policy_ok"] and f["total_inr"] == f["fare_inr"] * 2 and f["why"])
        self.assertTrue(any("outside" in b["reason"] for b in bad))

    def test_business_is_out_of_policy_on_a_short_route(self):
        req = {"from_city": "Mumbai", "to_city": "Pune", "pax": 1}
        top, bad = rank_flights(search_flights("Mumbai", "Pune", "2026-10-28", 1, "business"), req)
        self.assertEqual(top, [])
        self.assertTrue(any("Business class" in b["reason"] for b in bad))

    def test_cheapest_in_policy_flight_is_first(self):
        req = {"from_city": "Mumbai", "to_city": "Pune", "pax": 1}
        options = search_flights("Mumbai", "Pune", "2026-10-28", 1)
        top, _ = rank_flights(options, req)
        w = POLICY["depart_window"]
        legal = [f for f in options if w["from"] <= f["depart_time"] <= w["to"] and f["seats_left"] >= 1]
        self.assertEqual(top[0]["fare_inr"], min(f["fare_inr"] for f in legal))

    def test_hotels_at_or_under_the_city_rate_then_cheapest(self):
        req = {"to_city": "Delhi", "nights": 2, "rooms": 1}
        top, bad = rank_hotels(search_hotels("Delhi", "2026-11-02", 2, 1), req)
        self.assertEqual(len(top), 3)
        self.assertTrue(all(h["rate_inr"] <= POLICY_RATE["Delhi"] for h in top))
        self.assertEqual([h["rate_inr"] for h in top], sorted(h["rate_inr"] for h in top))
        self.assertTrue(all(h["total_inr"] == h["rate_inr"] * 2 for h in top))
        self.assertTrue(all(b["kind"] == "hotel" for b in bad))


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="travel_test_")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.cos = build_company_os(agents=("travel_booking",), state_dir=self.dir)
        self.addCleanup(close_all, self.cos)

    def bookings(self):
        return self.cos.memory.conn.execute("SELECT COUNT(*) FROM travel_bookings").fetchone()[0]

    def test_same_inputs_give_the_same_options(self):
        a = service.request_trip(self.cos, "P05", TEXT)
        b = service.request_trip(self.cos, "P05", TEXT)
        self.assertEqual((a["flights"], a["hotels"]), (b["flights"], b["hotels"]))

    def test_run_ends_held_with_one_approval_and_a_letter(self):
        r = service.request_trip(self.cos, "P05", TEXT)
        self.assertEqual((r["ok"], r["status"]), (True, "held"))
        self.assertEqual((len(r["flights"]), len(r["hotels"])), (3, 3))
        pending = self.cos.approvals.pending()
        self.assertEqual([p["approval_id"] for p in pending], [r["approval_id"]])
        self.assertEqual(pending[0]["tool"], "book_travel")
        mail = self.cos.outbox.messages("P05")
        self.assertEqual((len(mail), mail[0]["kind"], mail[0]["text"]), (1, "travel_options", r["letter"]))
        self.assertEqual(len(r["round_trips"]), 3)
        for rt in r["round_trips"]:
            for leg in (rt["outbound"], rt["return"]):
                self.assertIn(leg["flight_no"], r["letter"])
            self.assertEqual(rt["fare_inr"], rt["outbound"]["fare_inr"] + rt["return"]["fare_inr"])
            self.assertEqual(rt["total_inr"], rt["fare_inr"] * 3)
        self.assertEqual(self.cos.memory.get_run(r["run_id"])["status"], "held")

    def test_nothing_is_booked_before_approval(self):
        r = service.request_trip(self.cos, "P05", TEXT)
        self.assertEqual(self.bookings(), 0)
        self.assertEqual(service.booking_after_approval(self.cos, r["approval_id"])["status"], "skipped")
        self.assertEqual(self.bookings(), 0)

    def test_deny_books_nothing(self):
        r = service.request_trip(self.cos, "P05", TEXT)
        self.cos.approvals.decide(r["approval_id"], False, "P01")
        self.assertEqual(service.booking_after_approval(self.cos, r["approval_id"])["status"], "skipped")
        self.assertEqual(self.bookings(), 0)
        self.assertEqual(service.requests_for(self.cos, "P05")[0]["status"], "denied")

    def test_approve_books_once(self):
        r = service.request_trip(self.cos, "P05", TEXT)
        self.cos.approvals.decide(r["approval_id"], True, "P01")
        first = service.booking_after_approval(self.cos, r["approval_id"])
        self.assertEqual(first["status"], "booked")
        self.assertTrue(first["booking_ref"].startswith("SIM-"))
        self.assertEqual(service.booking_after_approval(self.cos, r["approval_id"])["status"], "skipped")
        self.assertEqual(self.bookings(), 1)
        row = service.requests_for(self.cos, "P05")[0]
        self.assertEqual((row["status"], row["booking_ref"]), ("booked", first["booking_ref"]))
        self.assertEqual(row["total_inr"], r["round_trips"][0]["total_inr"] + r["hotels"][0]["total_inr"])

    def test_choose_options_replaces_the_held_approval(self):
        r = service.request_trip(self.cos, "P05", TEXT)
        c = service.choose_options(self.cos, r["request_id"], r["round_trips"][1]["option_id"], r["hotels"][2]["option_id"], "P05")
        self.assertTrue(c["ok"])
        self.assertNotEqual(c["approval_id"], r["approval_id"])
        self.assertEqual(self.cos.approvals.get(r["approval_id"])["status"], "rejected")
        self.assertEqual([p["approval_id"] for p in self.cos.approvals.pending()], [c["approval_id"]])
        self.cos.approvals.decide(c["approval_id"], True, "P01")
        self.assertEqual(service.booking_after_approval(self.cos, c["approval_id"])["status"], "booked")
        self.assertEqual(self.cos.memory.conn.execute("SELECT flight_option_id, hotel_option_id FROM travel_bookings").fetchone()[:],
                         (r["round_trips"][1]["option_id"], r["hotels"][2]["option_id"]))

    def test_choose_options_refuses_bad_choices(self):
        r = service.request_trip(self.cos, "P05", TEXT)
        f, h = r["round_trips"][0]["option_id"], r["hotels"][0]["option_id"]
        self.assertFalse(service.choose_options(self.cos, r["request_id"], "FL-nope", h, "P05")["ok"])
        self.assertFalse(service.choose_options(self.cos, r["request_id"], f, None, "P05")["ok"])
        self.assertFalse(service.choose_options(self.cos, r["request_id"], f, h, "P03")["ok"])   # another person's request
        self.assertTrue(service.choose_options(self.cos, r["request_id"], f, h, "P01")["ok"])    # an Admin may choose
        self.assertEqual(len(self.cos.approvals.pending()), 1)

    def test_wrong_role_approval_does_not_book(self):
        r = service.request_trip(self.cos, "P05", TEXT)
        self.cos.approvals.decide(r["approval_id"], True, "P02")   # rnd_lead may start but not approve travel
        self.assertEqual(service.booking_after_approval(self.cos, r["approval_id"])["status"], "skipped")
        self.assertEqual(self.bookings(), 0)

    def test_csm_sees_own_requests_admin_sees_all(self):
        mine = service.request_trip(self.cos, "P05", TEXT)
        other = service.request_trip(self.cos, "P03", "flights for 2 people Delhi to Mumbai on 2026-11-03")
        self.assertEqual([x["request_id"] for x in service.requests_for(self.cos, "P05")], [mine["request_id"]])
        self.assertEqual([x["request_id"] for x in service.requests_for(self.cos, "P05", all_requests=True)], [mine["request_id"]])
        self.assertEqual({x["request_id"] for x in service.requests_for(self.cos, "P01", all_requests=True)},
                         {mine["request_id"], other["request_id"]})
        self.assertEqual([x["request_id"] for x in service.requests_for(self.cos, "P01")], [])

    def test_spend_rules_read_the_policy_file(self):
        import importlib
        spend_tools = importlib.import_module("control_plane.connectors.spend_tools")
        self.assertEqual((spend_tools.LATE_DAYS, spend_tools.MIN_SAVING_SHARE, spend_tools.SHORT_FLIGHT_HOURS,
                          spend_tools.SAME_CITY_DAYS, spend_tools.HOTEL_OVER_SHARE),
                         (POLICY["late_booking_days"], POLICY["earlier_fare_min_saving_share"], POLICY["economy_only_under_hours"],
                          POLICY["same_city_days"], POLICY["hotel_over_city_rate_share"]))

    def test_way_in_gives_each_person_only_their_own_scope(self):
        from contract.types import Task

        def admit(caller, area):
            return self.cos.way_in.admit(Task(agent="travel_booking", caller_id=caller, area_id=area, trigger_kind="request")).verdict
        for person in ("P01", "P05", "P03"):  # Admin, CSM and Growth each use the DevX internal area
            self.assertEqual(admit(person, "devx-internal"), "allow", person)
        self.assertEqual(admit("P05", "C07"), "deny")   # a client area the CSM does not look after
        self.assertEqual(admit("P03", "hold"), "deny")
        self.assertEqual(admit("P11", "devx-internal"), "deny")  # an engineer may not start the agent
        mine = service.request_trip(self.cos, "P05", TEXT)
        theirs = service.request_trip(self.cos, "P03", TEXT)
        self.assertEqual([x["request_id"] for x in service.requests_for(self.cos, "P03")], [theirs["request_id"]])
        self.assertNotIn(mine["request_id"], [x["request_id"] for x in service.requests_for(self.cos, "P03", all_requests=True)])

    def test_no_return_date_means_flights_only(self):
        r = service.request_trip(self.cos, "P03", "flights for 2 people Delhi to Mumbai on 2026-11-03")
        self.assertEqual((r["status"], len(r["flights"]), r["hotels"]), ("held", 3, []))

    def test_refusals_book_and_hold_nothing(self):
        bad = service.request_trip(self.cos, "P05", "2 people Mumbai to Goa on 2026-10-28")
        self.assertEqual((bad["status"], bad["ok"]), ("refused", False))
        engineer = self.cos.data_conn.execute("SELECT person_id FROM people WHERE role = 'engineer' LIMIT 1").fetchone()[0]
        denied = service.request_trip(self.cos, engineer, TEXT)
        self.assertEqual(denied["status"], "refused")
        stranger = service.request_trip(self.cos, "P999", TEXT)
        self.assertEqual(stranger["status"], "refused")
        self.assertEqual(self.cos.approvals.pending(), [])

    def test_letter_names_no_person_and_no_other_trip(self):
        r = service.request_trip(self.cos, "P05", TEXT)
        for (name,) in self.cos.data_conn.execute("SELECT name FROM people"):
            self.assertIsNone(re.search(rf"\b{name.split()[0]}\b", r["letter"]))
        self.assertNotRegex(r["letter"], r"\bTR\d{3}\b")

    def test_pack_check_rejects_a_bad_letter(self):
        pack = self.cos.packs["travel_booking"]
        r = service.request_trip(self.cos, "P05", TEXT)
        t = {"request": {"pax": 3, "nights": 1, "rooms": 2}, "flights": r["flights"], "round_trips": r["round_trips"],
             "hotels": [], "out_of_policy": []}
        ctx = type("C", (), {"notes": {}})()
        good = {"letter": r["letter"].split("\n\nBest hotels")[0] + "\n\nNothing is booked yet."}
        self.assertEqual(pack.check(ctx, good, t), [])
        self.assertTrue(pack.check(ctx, {"letter": good["letter"] + " INR 9,99,999"}, t))
        self.assertTrue(pack.check(ctx, {"letter": good["letter"] + " Akbar Ali also flies."}, t))
        self.assertTrue(pack.check(ctx, {"letter": good["letter"] + " See TR012."}, t))
        self.assertTrue(pack.check(ctx, {"letter": "KSA 111 is great. Nothing is booked yet."}, t))
        self.assertTrue(pack.check(ctx, {"letter": good["letter"].replace("Nothing is booked", "It is done")}, t))
        wrong_rt = {**t, "round_trips": [{**r["round_trips"][0], "total_inr": 5}, *r["round_trips"][1:]]}
        self.assertTrue(pack.check(ctx, good, wrong_rt))
        wrong = {**t, "round_trips": [], "flights": [{**r["flights"][0], "total_inr": 5}]}
        self.assertTrue(pack.check(ctx, good, wrong))
        self.assertTrue(pack.check(ctx, good, {**t, "flights": [{**r["flights"][0], "policy_ok": False}]}))


class ExamTests(unittest.TestCase):
    def test_travel_booking_exam_passes(self):
        d = tempfile.mkdtemp(prefix="travel_exam_")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        cos = build_company_os(agents=("travel_booking",), state_dir=d)
        self.addCleanup(close_all, cos)
        raw = replay_exam.run_exam(cos)
        self.assertTrue(replay_exam.judge(raw)[2], raw)
        self.assertEqual((raw["failed"], raw["policy_violations"], raw["booked_before_approval"]), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
