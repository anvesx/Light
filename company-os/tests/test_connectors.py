"""Tests for T5 connectors, on the real generated data: directory, sync, memory views, tools, planted signals."""
import json
import os
import unittest
from datetime import date, timedelta

from company_data import DB_PATH, connect
from company_data.generate_dummy_data import build
from control_plane.company_memory import MemoryStore
from control_plane.connectors import (PeopleDirectory, books_tools, event_area, meeting_tools, slack_tools, sync_meetings)
from control_plane.connectors.memory_views import open_items_as_of, recent_decisions_as_of
from control_plane.connectors.meetings_to_memory import meeting_area
from contract.types import RunContext, Task
from control_plane.triggers.request_trigger import parse_request

KEYS_PATH = os.path.join(os.path.dirname(DB_PATH), "answer_keys.json")
INTERNAL = "devx-internal"


def day(d, n):
    return (date.fromisoformat(d) + timedelta(days=n)).isoformat()


def setUpModule():
    global CONN, MEM, KEYS, TOOLS
    if not os.path.exists(DB_PATH):
        build()
    CONN = connect()
    with open(KEYS_PATH) as f:
        KEYS = json.load(f)
    MEM = MemoryStore(":memory:")
    sync_meetings(CONN, MEM)
    TOOLS = {t.name: t for t in (slack_tools(CONN) + meeting_tools(CONN) + books_tools(CONN))}


def call(name, area, **args):
    ctx = RunContext("R1", Task("test", "P01", area, "test"), MEM.scoped([area]))
    return json.loads(TOOLS[name].fn(args, ctx))


def case(group, case_id):
    return next(c for c in KEYS[group]["cases"] + KEYS[group]["look_alikes"] if c["case_id"] == case_id)


def project_area(project_id):
    return CONN.execute("SELECT client_id FROM projects WHERE project_id = ?", (project_id,)).fetchone()[0]


class DirectoryTests(unittest.TestCase):
    def setUp(self):
        self.d = PeopleDirectory(CONN)
        self.clients = {r[0] for r in CONN.execute("SELECT client_id FROM clients")}

    def test_ceo_and_rnd_lead_see_every_client(self):
        for pid in ("P01", "P02"):
            self.assertEqual(self.d.client_access(pid), self.clients | {INTERNAL})

    def test_csm_sees_own_clients_only(self):
        self.assertEqual(self.d.client_access("P05"), {"C01", "C04", "C06", INTERNAL})
        self.assertEqual(self.d.client_access("P06"), {"C02", "C03", "C05", INTERNAL})

    def test_account_manager_and_project_lead(self):
        self.assertNotIn("C01", self.d.client_access("P03"))  # v2: Growth reads prospects it owns, not won clients
        self.assertEqual(self.d.client_access("P03") - {INTERNAL}, self.d._deal_clients("P03"))
        self.assertIn("C02", self.d.client_access("P10"))

    def test_engineer_sees_client_with_time_logs_only(self):
        logged = {project_area(r[0]) for r in CONN.execute(
            "SELECT DISTINCT k.project_id FROM time_logs l JOIN tasks k ON k.task_id = l.task_id WHERE l.person_id = 'P12'")}
        self.assertEqual(self.d.client_access("P12"), logged | {INTERNAL})
        self.assertNotIn("C02", self.d.client_access("P12"))

    def test_every_devx_person_sees_internal_others_see_nothing(self):
        for r in CONN.execute("SELECT person_id, is_devx FROM people"):
            self.assertEqual(INTERNAL in self.d.client_access(r[0]), bool(r[1]))
        self.assertEqual(self.d.client_access("P90"), {INTERNAL})
        self.assertEqual(self.d.client_access("X01"), set())
        self.assertEqual(self.d.client_access("nobody"), set())

    def test_system_is_known_and_sees_all(self):
        self.assertEqual(self.d.role("system"), "system")
        self.assertIsNotNone(self.d.get("system"))
        self.assertEqual(self.d.client_access("system"), self.clients | {INTERNAL, "hold"})
        self.assertFalse(self.d.is_devx("system"))

    def test_lookups(self):
        self.assertIsNone(self.d.get("nobody"))
        self.assertNotIn("monthly_salary_inr", self.d.get("P12"))
        self.assertTrue(self.d.is_devx("P12"))
        self.assertFalse(self.d.is_devx("X01"))
        self.assertEqual(self.d.role("P05"), "csm")
        self.assertEqual(self.d.manager_of("P12"), "P08")
        self.assertEqual(self.d.csm_of("C02"), "P06")
        self.assertEqual(self.d.lead_of("PR03"), "P10")
        self.assertEqual(self.d.people_by_role("rnd_lead"), ["P02"])
        self.assertEqual(self.d.people_by_role("csm"), ["P05", "P06"])


class SyncTests(unittest.TestCase):
    def test_second_run_adds_nothing(self):
        self.assertEqual(sync_meetings(CONN, MEM), {"meetings": 112, "items_added": 0, "transcripts_added": 0,
                                                    "links_added": 0, "links_skipped": 0})

    def test_counts_match_data(self):
        n_items = CONN.execute("SELECT COUNT(*) FROM meeting_items").fetchone()[0]
        self.assertEqual(len(MEM.items(kinds=["transcript"])), 112)
        self.assertEqual(sum(len(MEM.items(kinds=[k])) for k in ("decision", "task", "question", "fact", "opinion")), n_items)

    def test_injection_meeting_in_its_client_area(self):
        mid = KEYS["injection"]["meeting_id"]
        client = CONN.execute("SELECT client_id FROM meetings WHERE meeting_id = ?", (mid,)).fetchone()[0]
        self.assertIsNotNone(client)
        texts = [i["text"] for i in MEM.items(client, kinds=["transcript"]) if i["source"] == f"meeting:{mid}"]
        self.assertEqual(len(texts), 1)
        self.assertIn(KEYS["injection"]["instruction"], texts[0])

    def test_no_item_lands_in_another_area(self):
        clients = {r["client_id"]: 1 for r in CONN.execute("SELECT client_id FROM clients")}
        meetings = {m["meeting_id"]: m for m in CONN.execute("SELECT * FROM meetings")}
        for item in MEM.items():
            self.assertEqual(item["area_id"], meeting_area(meetings[item["source"].split(":")[1]], clients))
            self.assertEqual(item["created_at"], meetings[item["source"].split(":")[1]]["start_at"])
        self.assertEqual(MEM.items("hold"), [])
        self.assertTrue(MEM.items(INTERNAL))

    def test_status_kept_and_links_dated_at_later_meeting(self):
        for row in CONN.execute("SELECT item_id, status FROM meeting_items LIMIT 40"):
            self.assertEqual(MEM.get_item(row["item_id"])["status"], row["status"])
        row = CONN.execute("SELECT item_id, answers_item_id FROM meeting_items WHERE answers_item_id IS NOT NULL").fetchone()
        link = next(l for l in MEM.links_of(row["item_id"]) if l["rel"] == "answers")
        self.assertEqual(link["to_id"], row["answers_item_id"])
        self.assertEqual(link["created_at"], MEM.get_item(row["item_id"])["created_at"])

    def test_until_skips_later_meetings(self):
        mem = MemoryStore(":memory:")
        counts = sync_meetings(CONN, mem, until="2026-06-01")
        self.assertLess(counts["meetings"], 112)
        self.assertTrue(all(i["created_at"] < "2026-06-01" for i in mem.items()))
        sync_meetings(CONN, mem)
        self.assertEqual(len(mem.items(kinds=["transcript"])), 112)


class MemoryViewTests(unittest.TestCase):
    def pair(self):
        for l in MEM.conn.execute("SELECT * FROM links WHERE rel = 'answers' ORDER BY created_at"):
            q = MEM.get_item(l["to_id"])
            if q["kind"] == "question" and q["created_at"][:10] < day(l["created_at"][:10], -1):
                return q, l
        self.fail("no answered question found")

    def test_answered_item_hidden_after_and_shown_before(self):
        q, link = self.pair()
        view = MEM.scoped([q["area_id"]])
        shown = lambda as_of: q["item_id"] in {i["item_id"] for i in open_items_as_of(view, q["area_id"], as_of)}
        a = link["created_at"][:10]
        self.assertTrue(shown(day(a, -1)))
        self.assertTrue(shown(link["created_at"]))      # not yet answered at that exact moment
        self.assertFalse(shown(day(a, 1)))
        self.assertFalse(shown("2026-10-19"))

    def test_item_not_shown_before_it_exists(self):
        q, _ = self.pair()
        view = MEM.scoped([q["area_id"]])
        ids = {i["item_id"] for i in open_items_as_of(view, q["area_id"], q["created_at"])}
        self.assertNotIn(q["item_id"], ids)

    def test_decisions_window_and_supersede(self):
        row = CONN.execute("SELECT item_id, supersedes_item_id FROM meeting_items WHERE supersedes_item_id IS NOT NULL").fetchone()
        old, new = MEM.get_item(row["supersedes_item_id"]), MEM.get_item(row["item_id"])
        view = MEM.scoped([old["area_id"]])
        ids = lambda as_of: {d["item_id"] for d in recent_decisions_as_of(view, old["area_id"], as_of, days=400)}
        if old["kind"] == "decision":
            self.assertIn(old["item_id"], ids(day(new["created_at"][:10], -1)) | ids(new["created_at"]))
            self.assertNotIn(old["item_id"], ids(day(new["created_at"][:10], 1)))
        for d in recent_decisions_as_of(view, old["area_id"], "2026-10-19", days=10):
            self.assertGreaterEqual(d["created_at"], "2026-10-09")


class ToolAreaTests(unittest.TestCase):
    CLIENT = {"client_channel_activity", "recent_client_messages", "upcoming_meeting", "project_open_items",
              "project_recent_decisions"}
    BOOKS = {"invoices_window", "payments_window", "budget_vs_spend", "travel_share_of_salary"}

    def test_every_tool_is_known(self):
        self.assertEqual(set(TOOLS), self.CLIENT | self.BOOKS)
        self.assertTrue(TOOLS["recent_client_messages"].reads_outside_text)

    def test_wrong_area_gets_error(self):
        allowed = {**{n: {"C01", "C02", "C03", "C04", "C05", "C06"} for n in self.CLIENT},
                   **{n: {INTERNAL} for n in self.BOOKS}}
        for n in ("upcoming_meeting", "project_open_items", "project_recent_decisions"):
            allowed[n] = allowed[n] | {INTERNAL}
        for name, ok in allowed.items():
            for area in ("C01", "C02", INTERNAL, "hold"):
                out = call(name, area)
                if area in ok:
                    self.assertNotIn("error", out, f"{name} {area}")
                else:
                    self.assertIn("error", out, f"{name} {area}")

    def test_other_area_argument_refused(self):
        self.assertIn("error", call("client_channel_activity", "C01", client_id="C02"))
        self.assertIn("error", call("upcoming_meeting", "C01", event_id="EV113"))
        self.assertIn("error", call("client_channel_activity", "C01", as_of="19/10/2026"))

    def test_rows_stay_in_area(self):
        for area in ("C01", "C05"):
            msgs = call("recent_client_messages", area, days=180, limit=60)["messages"]
            self.assertTrue(msgs)
            self.assertEqual({CONN.execute("SELECT client_id FROM slack_messages WHERE msg_id = ?", (m["msg_id"],)).fetchone()[0]
                              for m in msgs}, {area})
            for key in ("items",):
                items = call("project_open_items", area, limit=150)[key]
                self.assertTrue(items)
                self.assertEqual({MEM.get_item(i["item_id"])["area_id"] for i in items}, {area})

    def test_memory_tools_use_scoped_memory(self):
        other = call("project_open_items", "C01", project_id="PR03")
        self.assertEqual(other["items"], [])

    def test_as_of_hides_later_rows(self):
        cut = "2026-07-01"
        for area in ("C01", "C03"):
            self.assertTrue(all(m["ts"][:10] <= cut for m in call("recent_client_messages", area, as_of=cut, days=180)["messages"]))
            self.assertTrue(all(i["created_at"][:10] <= cut for i in call("project_open_items", area, as_of=cut)["items"]))
            self.assertTrue(all(i["created_at"][:10] <= cut for i in call("project_recent_decisions", area, as_of=cut, days=365)["decisions"]))
        self.assertTrue(all(i["date"] <= cut for i in call("invoices_window", INTERNAL, as_of=cut, days=365)["invoices"]))
        self.assertTrue(all(p["date"] <= cut for p in call("payments_window", INTERNAL, as_of=cut, days=365)["payments"]))

    def test_injection_message_is_visible_as_data(self):
        row = CONN.execute("SELECT client_id, ts FROM slack_messages WHERE msg_id = ?", (KEYS["injection"]["msg_id"],)).fetchone()
        msgs = call("recent_client_messages", row["client_id"], as_of=row["ts"][:10], days=5, limit=60)["messages"]
        self.assertIn(KEYS["injection"]["msg_id"], {m["msg_id"] for m in msgs})

    def test_event_lookup_with_request_trigger(self):
        lookup = event_area(CONN)
        self.assertEqual(lookup("EV07"), "C01")
        self.assertEqual(lookup("EV02"), INTERNAL)
        self.assertIsNone(lookup("EV999"))
        self.assertEqual(parse_request("prep me for EV113", "P10", lookup).area_id, "C02")
        self.assertEqual(parse_request("prep me for EV999", "P10", lookup).area_id, "hold")

    def test_upcoming_meeting(self):
        ev = call("upcoming_meeting", "C01")["events"]
        self.assertEqual([e["event_id"] for e in ev], ["EV114"])
        self.assertTrue(any(a["person_id"] == "X01" and not a["is_devx"] for a in ev[0]["attendees"]))
        self.assertEqual(call("upcoming_meeting", "C02", event_id="EV113")["events"][0]["project_id"], "PR03")
        self.assertEqual(call("upcoming_meeting", "C01", as_of="2026-10-10", days=1)["events"], [])


class PlantedSignalTests(unittest.TestCase):
    def on_and_before(self, group, case_id, check):
        c = case(group, case_id)
        first = c["first_detectable_on"]
        self.assertTrue(check(c, first), f"{case_id} not visible on {first}")
        self.assertFalse(check(c, day(first, -1)), f"{case_id} visible the day before")






    def duplicate_pair(self, vendor_id, d):
        rows = call("invoices_window", INTERNAL, as_of=d, days=90, vendor_id=vendor_id)["invoices"]
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if a["amount_inr"] == b["amount_inr"] and (date.fromisoformat(b["date"]) - date.fromisoformat(a["date"])).days <= 10:
                    return a, b
        return None

    def test_fin_1_to_3_duplicate_invoices(self):
        for cid in ("FIN-1", "FIN-2", "FIN-3"):
            self.on_and_before("finance_watch", cid, lambda c, d: self.duplicate_pair(c["vendor_id"], d) is not None)
            c = case("finance_watch", cid)
            a, b = self.duplicate_pair(c["vendor_id"], c["first_detectable_on"])
            self.assertEqual({a["invoice_id"], b["invoice_id"]}, set(c["invoice_ids"]))

    def test_monthly_subscriptions_are_not_duplicates(self):
        for vendor in case("finance_watch", "FIN-L1")["vendor_ids"]:
            self.assertIsNone(self.duplicate_pair(vendor, "2026-10-19"), vendor)

    def test_fin_4_5_large_payment_to_new_vendor(self):
        def check(c, d):
            rows = call("payments_window", INTERNAL, as_of=d, min_amount_inr=500001)["payments"]
            return any(r["payment_id"] == c["payment_id"] and r["vendor_age_days"] < 30 for r in rows)
        for cid in ("FIN-4", "FIN-5"):
            self.on_and_before("finance_watch", cid, check)

    def test_large_payment_to_old_vendor_is_distinguishable(self):
        c = case("finance_watch", "FIN-L2")
        rows = call("payments_window", INTERNAL, as_of="2026-10-19", days=365, min_amount_inr=500001)["payments"]
        row = next(r for r in rows if r["payment_id"] == c["payment_id"])
        self.assertGreaterEqual(row["vendor_age_days"], 30)

    def test_fin_6_7_budget_overrun(self):
        def check(c, d):
            rows = call("budget_vs_spend", INTERNAL, as_of=d, month=c["month"], team=c["team"])["rows"]
            return any(r["category"] == c["category"] and r["over_budget"] for r in rows)
        for cid in ("FIN-6", "FIN-7"):
            self.on_and_before("finance_watch", cid, check)
        over = [r for r in call("budget_vs_spend", INTERNAL, month="2026-08")["rows"] if r["over_budget"]]
        self.assertEqual([(r["team"], r["category"]) for r in over], [("design", "hardware")])

    def test_fin_8_travel_share_of_salary(self):
        def check(c, d):
            rows = call("travel_share_of_salary", INTERNAL, as_of=d, month=c["month"])["rows"]
            return next(r for r in rows if r["team"] == c["team"])["travel_share_of_salary"] >= 0.20
        self.on_and_before("finance_watch", "FIN-8", check)

    def test_travel_share_hides_one_person_salary(self):
        rows = call("travel_share_of_salary", INTERNAL)["rows"]
        for r in rows:
            if r["headcount"] < 3:
                self.assertIsNone(r["team_salary_total_inr"])
        text = json.dumps(rows)
        for (salary,) in CONN.execute("SELECT monthly_salary_inr FROM people WHERE person_id IN ('P01', 'P02', 'P07')"):
            self.assertNotIn(f":{salary},", text.replace(" ", ""))


if __name__ == "__main__":
    unittest.main()
