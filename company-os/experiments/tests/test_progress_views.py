"""Tests for the role-based progress views: each role sees the right shape and HR sees no person ids."""
import json
import re
import tempfile
import unittest

from connectors.progress_views import STATUSES, progress_for
from wiring.build_company_os import build_company_os

TODAY = "2026-10-19"
ALL_PROJECTS = ["PR01", "PR02", "PR03", "PR04", "PR05", "PR06"]


class ProgressViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._dir = tempfile.TemporaryDirectory()
        cls.cos = build_company_os(agents=("delivery_progress",), state_dir=cls._dir.name)
        for client in ("C01", "C02", "C03", "C04", "C05"):
            cls.cos.run("delivery_progress", "system", client, trigger_kind="timer", inputs={"as_of": TODAY})
        cls.cos.run("delivery_progress", "system", "C04", trigger_kind="timer", inputs={"as_of": "2026-09-01"})

    @classmethod
    def tearDownClass(cls):
        cls._dir.cleanup()

    def view(self, person_id, as_of=None):
        c = self.cos
        return progress_for(person_id, c.memory, c.directory, c.data_conn, as_of=as_of)

    def test_csm_sees_full_detail_for_own_projects_and_a_line_for_the_rest(self):
        v = self.view("P05")
        self.assertEqual(v["view"], "own_detail")
        self.assertEqual([p["project_id"] for p in v["projects"]], ["PR01", "PR02", "PR05"])
        self.assertIn("scope", v["projects"][0])
        self.assertEqual(v["other_projects"], [])
        v = self.view("P06")
        self.assertEqual([p["project_id"] for p in v["projects"]], ["PR03", "PR04", "PR06"])

    def test_project_lead_sees_own_detail_and_access_lines(self):
        v = self.view("P08")
        self.assertEqual([p["project_id"] for p in v["projects"]], ["PR01", "PR04"])
        self.assertEqual([p["project_id"] for p in v["other_projects"]], ["PR02"])
        self.assertEqual(set(v["other_projects"][0]), {"client_id", "client_name", "project_id", "project_name", "status"})

    def test_ceo_and_rnd_lead_see_all_projects_in_full(self):
        for person in ("P01", "P02"):
            v = self.view(person)
            self.assertEqual(v["view"], "full")
            self.assertEqual([p["project_id"] for p in v["projects"]], ALL_PROJECTS)
            self.assertTrue(all("scope" in p and "pace" in p for p in v["projects"]))

    def test_hr_sees_team_totals_without_person_ids_or_names(self):
        v = self.view("P90")
        self.assertEqual(v["view"], "team_totals")
        totals = v["totals"]
        self.assertEqual(totals["projects"], 6)
        self.assertEqual(sum(totals["by_status"].values()), 6)
        self.assertEqual(totals["by_status"]["behind"], 1)
        self.assertEqual(totals["scope_items"]["total"], 72)
        self.assertNotIn("projects", v)
        text = json.dumps(v)
        self.assertFalse(re.findall(r"\b[PXS]\d{2,3}\b", text))
        for r in self.cos.data_conn.execute("SELECT name FROM people"):
            self.assertNotIn(r[0], text)

    def test_growth_sees_one_status_line_per_project(self):
        v = self.view("P03")
        self.assertEqual(v["view"], "status_lines")
        self.assertEqual([p["project_id"] for p in v["projects"]], ALL_PROJECTS)
        for line in v["projects"]:
            self.assertEqual(set(line), {"client_id", "client_name", "project_id", "project_name", "status"})
            self.assertIn(line["status"], STATUSES)
        self.assertEqual(next(p for p in v["projects"] if p["project_id"] == "PR05")["status"], "behind")

    def test_other_roles_see_only_accessible_projects_one_line_each(self):
        allowed = self.cos.directory.client_access("P12")
        v = self.view("P12")
        self.assertEqual(v["view"], "status_lines")
        self.assertTrue(v["projects"])
        self.assertTrue(all(p["client_id"] in allowed and "scope" not in p for p in v["projects"]))
        self.assertLess(len(v["projects"]), 6)

    def test_people_without_access_see_nothing(self):
        self.assertEqual(self.view("X01")["projects"], [])
        self.assertEqual(self.view("nobody")["projects"], [])

    def test_as_of_picks_the_latest_snapshot_up_to_that_date(self):
        old = self.view("P01", as_of="2026-09-01")["projects"]
        self.assertEqual([(p["project_id"], p["as_of"]) for p in old], [("PR05", "2026-09-01")])
        self.assertEqual(self.view("P01", as_of="2026-08-01")["projects"], [])
        self.assertEqual({p["as_of"] for p in self.view("P01")["projects"]}, {TODAY})


if __name__ == "__main__":
    unittest.main()
