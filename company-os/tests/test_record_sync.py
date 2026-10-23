"""Record sync: areas, projects, deals, revenue and accepted SOW changes reach the brain, and a second run adds nothing."""
import tempfile
import unittest

from control_plane.company_brain.record_sync import STAGE_OF_LEAD, sync_records
from wiring.build_company_os import build_company_os


class RecordSyncCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.cos = build_company_os(agents=(), state_dir=cls.tmp.name)
        cls.counts = sync_records(cls.cos.data_conn, cls.cos.brain)

    @classmethod
    def tearDownClass(cls):
        for part in (cls.cos.data_conn, cls.cos.memory, cls.cos.outbox, cls.cos.approvals):
            part.close()
        cls.tmp.cleanup()

    def test_deals_follow_the_lead_stage_mapping(self):
        rows = {d["deal_id"]: d for d in self.cos.brain.deals([f"C{n:02d}" for n in range(1, 11)])}
        self.assertEqual(rows["L20"]["stage"], "closing")
        self.assertEqual(rows["L21"]["stage"], "proposal")
        self.assertEqual((rows["L22"]["stage"], rows["L23"]["stage"], rows["L05"]["stage"]), ("lost", "lost", "won"))
        self.assertEqual(rows["L20"]["owner_id"], "P03")
        self.assertEqual(STAGE_OF_LEAD["qualified"], "discovery")

    def test_projects_and_revenue(self):
        self.assertEqual([p["project_id"] for p in self.cos.brain.projects(["C04"])], ["PR05"])
        self.assertGreater(len(self.cos.brain.revenue(["C04"])), 3)
        self.assertEqual(self.counts["areas"], 10)

    def test_only_accepted_sow_changes_become_requirement_items(self):
        texts = [i["text"] for i in self.cos.brain.brain_items(["C01"], kinds=["requirement"])]
        self.assertIn("Add a gift voucher balance check at billing", texts)
        self.assertNotIn("Add a size recommendation quiz", texts)  # SC05 was not accepted
        item = next(i for i in self.cos.brain.brain_items(["C04"]) if "insurance claim" in i["text"])
        self.assertEqual(item["topic"], "insurance-claims")
        self.assertEqual(item["evidence"][0]["quote_raw"], "Add insurance claim upload")
        self.assertEqual(self.cos.brain.get_source(item["facts"]["source_id"])["kind"], "record")

    def test_second_run_adds_nothing(self):
        before = len(self.cos.brain.brain_items([f"C{n:02d}" for n in range(1, 11)]))
        again = sync_records(self.cos.data_conn, self.cos.brain)
        self.assertEqual(again["items_added"], 0)
        self.assertEqual(len(self.cos.brain.brain_items([f"C{n:02d}" for n in range(1, 11)])), before)

    def test_until_leaves_out_later_changes_and_months(self):
        with tempfile.TemporaryDirectory() as tmp:
            cos = build_company_os(agents=(), state_dir=tmp)
            try:
                counts = sync_records(cos.data_conn, cos.brain, until="2026-05-01")
                self.assertLess(counts["items_added"], self.counts["items_added"])
                self.assertTrue(all(r["month"] <= "2026-05" for r in cos.brain.revenue(["C01", "C04"])))
            finally:
                for part in (cos.data_conn, cos.memory, cos.outbox, cos.approvals):
                    part.close()

    def test_existing_deal_tags_are_kept(self):
        self.cos.brain.upsert_deal(deal_id="L20", area_id="C07", tags=["pilot"])
        sync_records(self.cos.data_conn, self.cos.brain)
        self.assertEqual(next(d for d in self.cos.brain.deals(["C07"]) if d["deal_id"] == "L20")["tags"], ["pilot"])


if __name__ == "__main__":
    unittest.main()
