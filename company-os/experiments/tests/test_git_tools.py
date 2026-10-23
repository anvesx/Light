"""Tests for the git read tools: area guard, as_of dates, planted signals and no developer data."""
import json
import os
import unittest

from company_data import DB_PATH, connect
from company_data.generate_dummy_data import build
from company_memory import MemoryStore
from connectors.git_tools import git_tools
from contract.types import RunContext, Task

KEYS_PATH = os.path.join(os.path.dirname(DB_PATH), "answer_keys.json")


def setUpModule():
    global CONN, MEM, KEYS, TOOLS
    if not os.path.exists(DB_PATH):
        build()
    CONN = connect()
    MEM = MemoryStore(":memory:")
    with open(KEYS_PATH) as f:
        KEYS = json.load(f)["delivery_progress"]
    TOOLS = {t.name: t for t in git_tools(CONN)}


def raw(name, area, **args):
    ctx = RunContext("R1", Task("delivery_progress", "P05", area, "test"), MEM.scoped([area]))
    return TOOLS[name].fn(args, ctx)


def call(name, area, **args):
    return json.loads(raw(name, area, **args))


def case(case_id):
    return next(c for c in KEYS["cases"] + KEYS["look_alikes"] if c["case_id"] == case_id)


def area_of(project_id):
    return CONN.execute("SELECT client_id FROM projects WHERE project_id = ?", (project_id,)).fetchone()[0]


class GitToolGuardTests(unittest.TestCase):
    def test_internal_area_is_refused(self):
        for name in TOOLS:
            self.assertIn("error", call(name, "devx-internal"))

    def test_other_clients_arguments_are_refused(self):
        for name in TOOLS:
            self.assertIn("error", call(name, "C01", client_id="C02"))
        self.assertIn("error", call("scope_burndown", "C01", project_id="PR03"))
        self.assertIn("error", call("unlinked_merged_prs", "C01", project_id="PR03"))
        self.assertIn("error", call("project_pace", "C01", project_id="PR03"))
        self.assertIn("error", call("scope_burndown", "C01", pr_id=CONN.execute(
            "SELECT pr_id FROM pull_requests WHERE project_id = 'PR03' LIMIT 1").fetchone()[0]))

    def test_rows_stay_in_the_area(self):
        projects = {p["project_id"] for p in call("scope_burndown", "C01")["projects"]}
        self.assertEqual(projects, {"PR01", "PR02"})
        self.assertEqual({p["project_id"] for p in call("unlinked_merged_prs", "C01")["prs"]}, {"PR01", "PR02"})

    def test_no_developer_is_named(self):
        for name in TOOLS:
            text = raw(name, "C01")
            for word in ("author", "assignee"):
                self.assertNotIn(word, text)
        authors = {r[0] for r in CONN.execute("SELECT DISTINCT author_id FROM pull_requests")}
        text = raw("unlinked_merged_prs", "C01") + raw("scope_burndown", "C01")
        self.assertFalse([a for a in authors if f'"{a}"' in text])

    def test_bad_as_of_is_an_error(self):
        self.assertIn("error", call("project_pace", "C01", as_of="soon"))


class GitToolDataTests(unittest.TestCase):
    def test_unlinked_prs_follow_as_of_and_mark_chores(self):
        del1 = case("DEL-1")
        first = del1["first_detectable_on"]
        today = call("unlinked_merged_prs", "C01")
        self.assertEqual(today["by_project"]["PR02"]["not_chore"], del1["count"])
        self.assertEqual(today["by_project"]["PR01"], {"merged_unlinked": 4, "not_chore": 0})
        self.assertTrue(all(p["chore"] for p in today["prs"] if p["project_id"] == "PR01"))
        on = call("unlinked_merged_prs", "C01", as_of=first)["by_project"]["PR02"]["not_chore"]
        before = call("unlinked_merged_prs", "C01", as_of="2026-08-25")["by_project"].get("PR02", {"not_chore": 0})
        self.assertEqual((on, before["not_chore"]), (3, 2))
        self.assertTrue(all(p["merged_on"] <= first for p in call("unlinked_merged_prs", "C01", as_of=first)["prs"]))

    def test_revisions_follow_as_of(self):
        item = case("DEL-2")["scope_item_id"]

        def revisions(as_of=None):
            args = {"as_of": as_of} if as_of else {}
            rows = call("scope_burndown", "C03", project_id="PR04", **args)["projects"][0]["scope"]
            return next(r["revisions"] for r in rows if r["id"] == item)
        self.assertEqual(revisions(), case("DEL-2")["count"])
        self.assertEqual(revisions(case("DEL-2")["first_detectable_on"]), 4)
        self.assertEqual(revisions("2026-09-28"), 3)
        la = next(r for r in call("scope_burndown", "C02")["projects"][0]["scope"] if r["id"] == case("DEL-L2")["scope_item_id"])
        self.assertEqual(la["revisions"], 2)

    def test_burndown_columns_and_future_hidden(self):
        scope = call("scope_burndown", "C03", project_id="PR04")["projects"][0]["scope"]
        for key in ("est", "tasks_done", "tasks_open", "prs_merged", "last_merge", "in_prod", "revisions"):
            self.assertIn(key, scope[0])
        early = call("scope_burndown", "C03", project_id="PR04", as_of="2026-07-01")["projects"][0]["scope"]
        late = call("scope_burndown", "C03", project_id="PR04")["projects"][0]["scope"]
        self.assertLess(sum(r["prs_merged"] for r in early), sum(r["prs_merged"] for r in late))
        self.assertTrue(all((r["last_merge"] or "") <= "2026-07-01" for r in early))
        self.assertEqual(call("scope_burndown", "C03", as_of="2026-05-01")["projects"], [])
        self.assertTrue(any(r["in_prod"] for r in late))

    def test_trigger_pr(self):
        pr = CONN.execute("SELECT pr_id FROM pull_requests WHERE project_id = 'PR02' AND task_id IS NULL "
                          "ORDER BY pr_id LIMIT 1").fetchone()[0]
        t = call("scope_burndown", "C01", pr_id=pr)["trigger_pr"]
        self.assertEqual((t["pr_id"], t["project_id"], t["scope_item_id"]), (pr, "PR02", None))

    def test_pace_matches_the_planted_cases(self):
        behind, ok = case("DEL-3"), case("DEL-L3")
        row = call("project_pace", area_of("PR05"))["projects"][0]
        self.assertAlmostEqual(row["merged_share"], behind["merged_share_today"], places=3)
        self.assertAlmostEqual(row["elapsed_share"], behind["elapsed_share_today"], places=3)
        self.assertEqual(row["projected_finish"], behind["projected_finish"])
        row = call("project_pace", area_of("PR06"))["projects"][0]
        self.assertAlmostEqual(row["merged_share"], ok["merged_share_today"], places=3)

    def test_pace_hides_the_future_and_paused_projects(self):
        self.assertEqual(call("project_pace", "C04", as_of="2026-06-01")["projects"], [])
        self.assertEqual(call("project_pace", "C06")["projects"], [])
        early = call("project_pace", "C04", as_of="2026-08-17")["projects"][0]
        self.assertEqual(early["pace_date"], "2026-08-17")


if __name__ == "__main__":
    unittest.main()
