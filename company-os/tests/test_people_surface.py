"""Tests for people_surface: private outbox and approval queue."""
import os
import tempfile
import unittest

from control_plane.people_surface import Approvals, DB_PATH, Outbox


class SurfaceTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = os.path.join(tmp.name, "surface.db")


class TestOutbox(SurfaceTestCase):
    def test_default_path(self):
        self.assertTrue(DB_PATH.endswith("people_surface/people_surface.db"))

    def test_post_and_list(self):
        box = Outbox(self.path)
        self.addCleanup(box.close)
        m1 = box.post("P05", "Brief for EV07", run_id="R000001", agent="meeting_prep", kind="brief")
        m2 = box.post("P09", "Hours over SOW", run_id="R000002", agent="finance_watch", kind="flag")
        self.assertNotEqual(m1, m2)
        self.assertEqual([m["msg_id"] for m in box.messages()], [m1, m2])
        only = box.messages("P05")
        self.assertEqual(len(only), 1)
        self.assertEqual((only[0]["text"], only[0]["agent"], only[0]["kind"], only[0]["run_id"]),
                         ("Brief for EV07", "meeting_prep", "brief", "R000001"))
        self.assertEqual(box.messages("P99"), [])

    def test_survives_reopen(self):
        box = Outbox(self.path)
        box.post("P05", "hi", run_id="R1", agent="a", kind="k")
        box.close()
        again = Outbox(self.path)
        self.addCleanup(again.close)
        self.assertEqual(len(again.messages()), 1)


class TestApprovals(SurfaceTestCase):
    def setUp(self):
        super().setUp()
        self.queue = Approvals(self.path)
        self.addCleanup(self.queue.close)

    def test_request_pending_decide(self):
        a1 = self.queue.request("R1", "finance_watch", "send_message", {"to": "P20"}, "reaches a person")
        a2 = self.queue.request("R2", "spend_advisor", "send_message", {"to": "S01"}, "risky")
        pending = self.queue.pending()
        self.assertEqual([p["approval_id"] for p in pending], [a1, a2])
        self.assertEqual(pending[0]["args"], {"to": "P20"})
        done = self.queue.decide(a1, True, "P01")
        self.assertEqual((done["status"], done["decided_by"]), ("approved", "P01"))
        self.assertEqual([p["approval_id"] for p in self.queue.pending()], [a2])
        self.assertEqual(self.queue.decide(a2, False, "P01")["status"], "rejected")
        self.assertEqual(self.queue.pending(), [])

    def test_decide_twice_or_unknown(self):
        a = self.queue.request("R1", "x", "t", {}, "why")
        self.queue.decide(a, True, "P01")
        with self.assertRaises(ValueError):
            self.queue.decide(a, False, "P02")
        with self.assertRaises(KeyError):
            self.queue.decide("ghost", True, "P01")


if __name__ == "__main__":
    unittest.main()
