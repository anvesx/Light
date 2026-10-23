"""Tests for T5 connectors, on the real generated data: directory, sync, memory views, tools, planted signals."""
import json
import os
import unittest
from datetime import date, timedelta

from company_data import DB_PATH, connect
from company_data.generate_dummy_data import build
from company_memory import MemoryStore
from connectors import (PeopleDirectory, books_tools, event_area, meeting_tools, project_tools, slack_tools,
                        staffing_tools, store_pos_tools, sync_meetings)
from connectors.memory_views import open_items_as_of, recent_decisions_as_of
from connectors.meetings_to_memory import meeting_area
from contract.types import RunContext, Task
from triggers.request_trigger import parse_request

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
    TOOLS = {t.name: t for t in (project_tools(CONN) + slack_tools(CONN) + meeting_tools(CONN) + books_tools(CONN)
                                 + store_pos_tools(CONN) + staffing_tools(CONN))}


def call(name, area, **args):
    ctx = RunContext("R1", Task("test", "P01", area, "test"), MEM.scoped([area]))
    return json.loads(TOOLS[name].fn(args, ctx))


def case(group, case_id):
    return next(c for c in KEYS[group]["cases"] + KEYS[group]["look_alikes"] if c["case_id"] == case_id)


def project_area(project_id):
    return CONN.execute("SELECT client_id FROM projects WHERE project_id = ?", (project_id,)).fetchone()[0]


class PlantedSignalTests(unittest.TestCase):
    def test_risk_1_hours_over_sow(self):
        def check(c, d):
            p = call("project_overview", project_area(c["project_id"]), as_of=d)["projects"]
            p = next(x for x in p if x["project_id"] == c["project_id"])
            return p["logged_pct_of_estimate"] > 115 and p["open_task_share"] >= 0.3
        self.on_and_before("project_risk", "RISK-1", check)

    def test_risk_2_client_silent_and_paused_look_alike(self):
        def check(c, d):
            p = call("client_channel_activity", project_area(c["project_id"]), as_of=d)["projects"]
            p = next(x for x in p if x["project_id"] == c["project_id"])
            return p["project_status"] == "active" and p["days_silent"] >= 14
        self.on_and_before("project_risk", "RISK-2", check)
        paused = call("client_channel_activity", "C06")["projects"][0]
        self.assertGreaterEqual(paused["days_silent"], 14)
        self.assertEqual(paused["project_status"], "paused")

    def test_risk_3_overloaded_engineer(self):
        def check(c, d):
            rows = call("weekly_hours_by_person", "C01", as_of=d, weeks=3)["rows"]
            weeks = [r for r in rows if r["person_id"] == c["person_id"] and r["week_complete"]]
            return len(weeks) == 3 and all(r["hours"] > 55 for r in weeks)
        self.on_and_before("project_risk", "RISK-3", check)

    def test_risk_4_overdue_tasks(self):
        def check(c, d):
            p = call("project_overview", project_area(c["project_id"]), as_of=d)["projects"]
            return next(x for x in p if x["project_id"] == c["project_id"])["tasks_overdue"] >= 5
        self.on_and_before("project_risk", "RISK-4", check)
        self.assertGreaterEqual(len(call("project_tasks", "C04", project_id="PR05", state="overdue")["tasks"]), 5)

    def test_look_alike_accepted_change_raises_estimate(self):
        c = case("project_risk", "RISK-L1")
        p = call("project_overview", "C05", as_of=c["naive_first_flag_on"])["projects"]
        p = next(x for x in p if x["project_id"] == "PR06")
        self.assertGreater(p["hours_logged"], 1.15 * p["sow_estimate_hours"])
        self.assertGreater(p["accepted_change_hours"], 0)
        self.assertLessEqual(p["logged_pct_of_estimate"], 115)
        today = next(x for x in call("project_overview", "C05")["projects"] if x["project_id"] == "PR06")
        self.assertLessEqual(today["logged_pct_of_estimate"], 115)
        pr03 = next(x for x in call("project_overview", "C02")["projects"] if x["project_id"] == "PR03")
        self.assertEqual(pr03["accepted_change_hours"], 0)   # PR03's change was never accepted

    def test_frd_1_many_cash_refunds(self):
        def check(c, d):
            r = self.staff_row("refunds_by_staff", "C01", c["person_id"], d)
            return r is not None and r["cash_refunds"] >= 5
        self.on_and_before("fraud_watch", "FRD-1", check)

    def test_frd_2_self_approved_discounts(self):
        def check(c, d):
            r = self.staff_row("discounts_by_staff", "C01", c["person_id"], d)
            return r is not None and r["self_approved"] >= 1
        self.on_and_before("fraud_watch", "FRD-2", check)
        self.assertEqual(self.staff_row("discounts_by_staff", "C01", "S13", "2026-10-19", days=365)["self_approved"], 8)

    def test_frd_3_free_remakes(self):
        def check(c, d):
            r = self.staff_row("remakes_by_staff", "C01", c["person_id"], d)
            return r is not None and r["free_remakes"] >= 5
        self.on_and_before("fraud_watch", "FRD-3", check)

    def test_recall_card_refunds_are_spread_over_staff(self):
        stores = {s["store_id"]: s for s in call("refunds_by_staff", "C01", days=365)["stores"]}
        st = stores["ST03"]
        self.assertGreaterEqual(st["by_reason"]["recall"], 20)
        self.assertGreaterEqual(st["distinct_staff"], 3)
        recall_staff = [r for r in call("refunds_by_staff", "C01", days=365, limit=60)["staff"] if r["store_id"] == "ST03"]
        self.assertTrue(all(r["cash_refunds"] < 5 for r in recall_staff))

    def test_sale_week_manager_approvals_are_not_self_approved(self):
        out = call("discounts_by_staff", "C01", days=365, limit=60)
        top = out["top_approvers"][0]
        self.assertEqual(top["approver_id"], "S01")
        self.assertGreaterEqual(top["distinct_requesters"], 3)
        self.assertTrue(all(r["self_approved"] == 0 for r in out["staff"] if r["staff_id"] == "S01"))
        self.assertEqual([r["staff_id"] for r in out["staff"] if r["self_approved"]], ["S13"])


class StaffingToolTests(unittest.TestCase):
    def test_capacity_and_remaining(self):
        teams = {t["team"]: t for t in call("team_capacity_and_load", INTERNAL)["teams"]}
        self.assertEqual(teams["engineering"]["capacity_hours_per_week"], 15 * 40)
        self.assertEqual(len(teams["engineering"]["weeks"]), 6)
        rows = {p["project_id"]: p for p in call("remaining_sow_hours", INTERNAL)["projects"]}
        self.assertNotIn("PR08", rows)
        self.assertNotIn("PR07", rows)
        self.assertEqual(rows["PR06"]["estimate_hours_with_changes"], 963 + 375)

    def test_pipeline_has_won_and_proposal(self):
        leads = {l["lead_id"]: l for l in call("pipeline_demand", INTERNAL)["leads"]}
        self.assertEqual(leads["L09"]["stage"], "proposal")
        self.assertFalse(leads["L09"]["started"])
        self.assertNotIn("L11", leads)


class ToolAreaTests(unittest.TestCase):
    CLIENT = {"project_overview", "project_tasks", "weekly_hours_by_person", "client_channel_activity",
              "recent_client_messages", "upcoming_meeting", "project_open_items", "project_recent_decisions"}
    BOOKS = {"invoices_window", "payments_window", "budget_vs_spend", "travel_share_of_salary", "team_capacity_and_load",
             "pipeline_demand", "remaining_sow_hours"}
    STORE = {"refunds_by_staff", "discounts_by_staff", "remakes_by_staff"}

    def test_every_tool_is_known(self):
        self.assertEqual(set(TOOLS), self.CLIENT | self.BOOKS | self.STORE)
        self.assertTrue(TOOLS["recent_client_messages"].reads_outside_text)

    def test_wrong_area_gets_error(self):
        allowed = {**{n: {"C01", "C02", "C03", "C04", "C05", "C06"} for n in self.CLIENT},
                   **{n: {INTERNAL} for n in self.BOOKS}, **{n: {"C01"} for n in self.STORE}}
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
        self.assertIn("error", call("project_overview", "C01", client_id="C02"))
        self.assertIn("error", call("project_tasks", "C01", project_id="PR03"))
        self.assertIn("error", call("upcoming_meeting", "C01", event_id="EV113"))
        self.assertIn("error", call("refunds_by_staff", "C01", store_id="ST99"))
        self.assertIn("error", call("project_overview", "C01", as_of="19/10/2026"))

    def test_rows_stay_in_area(self):
        for area in ("C01", "C05"):
            projects = {r[0] for r in CONN.execute("SELECT project_id FROM projects WHERE client_id = ?", (area,))}
            self.assertEqual({p["project_id"] for p in call("project_overview", area)["projects"]}, projects)
            self.assertTrue({t["project_id"] for t in call("project_tasks", area, state="all")["tasks"]} <= projects)
            msgs = call("recent_client_messages", area, days=180, limit=60)["messages"]
            self.assertTrue(msgs)
            self.assertEqual({CONN.execute("SELECT client_id FROM slack_messages WHERE msg_id = ?", (m["msg_id"],)).fetchone()[0]
                              for m in msgs}, {area})
            people = {r[0] for r in CONN.execute("SELECT DISTINCT person_id FROM time_logs l JOIN tasks k ON k.task_id = l.task_id "
                                                 "WHERE k.project_id IN (%s)" % ",".join("?" * len(projects)), tuple(projects))}
            hours = call("weekly_hours_by_person", area, weeks=12)["rows"]
            self.assertTrue({h["person_id"] for h in hours} <= people)
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
            self.assertTrue(all(p["start_on"] <= cut for p in call("project_overview", area, as_of=cut)["projects"]))
            self.assertTrue(all(m["ts"][:10] <= cut for m in call("recent_client_messages", area, as_of=cut, days=180)["messages"]))
            self.assertTrue(all(i["created_at"][:10] <= cut for i in call("project_open_items", area, as_of=cut)["items"]))
            self.assertTrue(all(i["created_at"][:10] <= cut for i in call("project_recent_decisions", area, as_of=cut, days=365)["decisions"]))
            hours = call("weekly_hours_by_person", area, as_of=cut, weeks=26)["rows"]
            self.assertTrue(all(h["week_start"] <= cut for h in hours))
        self.assertLess(call("project_overview", "C01", as_of=cut)["projects"][0]["hours_logged"],
                        call("project_overview", "C01")["projects"][0]["hours_logged"])
        self.assertTrue(all(i["date"] <= cut for i in call("invoices_window", INTERNAL, as_of=cut, days=365)["invoices"]))
        self.assertTrue(all(p["date"] <= cut for p in call("payments_window", INTERNAL, as_of=cut, days=365)["payments"]))
        self.assertTrue(all(w["week_start"] <= cut for t in call("team_capacity_and_load", INTERNAL, as_of=cut)["teams"] for w in t["weeks"]))
        leads = call("pipeline_demand", INTERNAL, as_of="2026-04-10")["leads"]
        self.assertEqual({l["lead_id"] for l in leads}, {"L08"})
        self.assertEqual({r["project_id"] for r in call("remaining_sow_hours", INTERNAL, as_of=cut)["projects"]} & {"PR09"}, set())
        for name in ("refunds_by_staff", "discounts_by_staff", "remakes_by_staff"):
            self.assertEqual(call(name, "C01", as_of="2026-03-31", days=365)["staff"], [])

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


class StaffRowHelper:
    """Helper the moved fraud tests used."""
    def staff_row(self, tool, area, staff_id, d, **args):
        rows = call(tool, area, as_of=d, **args)["staff"]
        return next((r for r in rows if r["staff_id"] == staff_id), None)
