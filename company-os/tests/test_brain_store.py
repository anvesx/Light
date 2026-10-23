"""Brain store: evidence rule, scoped reads, raw text fixed, reassign, review queue, library, retrieval."""
import os
import sqlite3
import tempfile
import unittest

from control_plane.company_brain import BrainStore, ScopedBrain
from control_plane.company_brain.retrieval import similar_deals
from control_plane.company_brain.sample_content import seed_sample
from control_plane.company_memory import AreaDenied, MemoryStore


def lines(*texts):
    return [{"line_no": n, "speaker": "A", "text": t} for n, t in enumerate(texts, start=1)]


class BrainCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.mem = MemoryStore(os.path.join(tmp.name, "m.db"))
        self.addCleanup(self.mem.close)
        self.brain = BrainStore(self.mem)
        self.data = sqlite3.connect(":memory:")
        self.data.row_factory = sqlite3.Row
        self.addCleanup(self.data.close)
        self.data.executescript("""
            CREATE TABLE clients (client_id TEXT, name TEXT, csm_id TEXT);
            CREATE TABLE people (person_id TEXT, name TEXT, email TEXT, role TEXT, is_devx INTEGER, client_id TEXT);
            INSERT INTO clients VALUES ('C01', 'Tailorbird', 'P05'), ('C04', 'MedBridge', NULL);
            INSERT INTO people VALUES ('P01', 'Ammar', 'ammar@devx.example', 'ceo', 1, NULL),
                ('P02', 'Dev', 'dev@devx.example', 'rnd_lead', 1, NULL), ('P05', 'Akbar Ali', 'akbar@devx.example', 'csm', 1, NULL),
                ('P03', 'Anthony', 'anthony@devx.example', 'growth', 1, NULL), ('P11', 'Ishaan', 'ishaan@devx.example', 'engineer', 1, NULL),
                ('X01', 'Dr Rao', 'rao@client.example', 'client_contact', 0, 'C04');
        """)
        self.brain.data_conn = self.data

    def source(self, area="C01", rows=("Hello there", "Reminders on WhatsApp"), **kw):
        return self.brain.add_source(area, "chat", "T", "\n".join(rows), origin_ref=kw.pop("origin_ref", "R1"),
                                     occurred_at="2026-10-01T10:00", participants=[], language="en", lines=lines(*rows), **kw)

    def item(self, sid, area="C01", **kw):
        args = dict(topic="reminders", source_id=sid, line_from=2, line_to=2, quote_raw="Reminders on WhatsApp",
                    quote_clean="Reminders on WhatsApp", confidence=0.9)
        args.update(kw)
        return self.brain.add_brain_item(area, "requirement", "Needs WhatsApp reminders", **args)


class TestItems(BrainCase):
    def test_item_has_evidence_and_facts(self):
        sid = self.source()
        item = self.item(sid, deal_id="L1", value="5")
        got = self.brain.brain_items(["C01"], deal_id="L1")[0]
        self.assertEqual(got["item_id"], item)
        self.assertEqual(got["evidence"][0]["quote_raw"], "Reminders on WhatsApp")
        self.assertEqual((got["facts"]["deal_id"], got["facts"]["confidence"], got["state"]), ("L1", 0.9, "active"))
        self.assertEqual(self.mem.get_item(item)["area_id"], "C01")

    def test_refuses_item_without_evidence(self):
        sid = self.source()
        for bad in ({"quote_raw": ""}, {"line_to": 9}, {"source_id": "SRC-999999"}, {"line_from": 0}):
            with self.assertRaises(ValueError):
                self.item(sid, **bad)
        self.assertEqual(self.brain.brain_items(["C01"], state=None), [])
        self.assertEqual(self.mem.items("C01"), [])

    def test_refuses_evidence_from_other_area(self):
        sid = self.source("C02")
        with self.assertRaises(ValueError):
            self.item(sid, area="C01")

    def test_state_filter_and_more_evidence(self):
        sid = self.source()
        item = self.item(sid)
        self.brain.add_evidence(item, sid, 1, 1, "Hello there", "Hello there")
        self.assertEqual(len(self.brain.brain_items(["C01"])[0]["evidence"]), 2)
        self.brain.set_state(item, "superseded")
        self.assertEqual(self.brain.brain_items(["C01"]), [])
        self.assertEqual(len(self.brain.brain_items(["C01"], state="superseded")), 1)
        with self.assertRaises(ValueError):
            self.brain.set_state(item, "bogus")


class TestSources(BrainCase):
    def test_raw_text_never_changes(self):
        sid = self.source()
        self.brain.set_clean_lines(sid, [{"line_no": 2, "clean_text": "Reminders on WhatsApp.", "speaker": "Anil"}])
        row = self.brain.source_lines(sid)[1]
        self.assertEqual((row["text"], row["clean_text"], row["clean_speaker"], row["speaker"]),
                         ("Reminders on WhatsApp", "Reminders on WhatsApp.", "Anil", "A"))
        with self.assertRaises(sqlite3.DatabaseError):
            self.mem.conn.execute("UPDATE brain_source_lines SET raw_text = 'x'")
        with self.assertRaises(sqlite3.DatabaseError):
            self.mem.conn.execute("UPDATE brain_sources SET raw_text = 'x'")
        self.assertEqual(self.brain.get_source(sid)["raw_text"], "Hello there\nReminders on WhatsApp")
        with self.assertRaises(KeyError):
            self.brain.set_clean_lines(sid, [{"line_no": 9, "clean_text": "x"}])

    def test_reassign_fails_once_items_exist(self):
        held = self.source("hold")
        self.mem.ensure_area("C04", kind="client")
        self.assertEqual(self.brain.get_source(held)["status"], "held")
        self.brain.reassign_source(held, "C04")
        self.assertEqual(self.brain.get_source(held)["area_id"], "C04")
        with self.assertRaises(ValueError):  # no longer on hold
            self.brain.reassign_source(held, "C01")
        held2 = self.source("hold", origin_ref="R2")
        self.brain.reassign_source(held2, "C04")
        self.assertEqual(self.brain.get_source(held2)["status"], "new")

    def test_reassign_refused_with_items_and_bad_target(self):
        held = self.source("hold")
        self.mem.ensure_area("C04", kind="client")
        with self.assertRaises(ValueError):
            self.brain.reassign_source(held, "devx-internal")
        # an item cannot be added on hold-area source for a client area, so add one in hold itself
        self.brain.add_brain_item("hold", "fact", "x", topic=None, source_id=held, line_from=1, line_to=1,
                                  quote_raw="Hello there", quote_clean="Hello there", confidence=0.5)
        with self.assertRaises(ValueError):
            self.brain.reassign_source(held, "C04")

    def test_list_filters_and_status(self):
        a = self.source("C01")
        self.source("C02", origin_ref="R2")
        self.brain.set_source_status(a, "cleaned")
        self.assertEqual([s["source_id"] for s in self.brain.sources(["C01", "C02"], status="cleaned")], [a])
        self.assertEqual(len(self.brain.sources(["C01", "C02"], kind="chat")), 2)
        self.assertEqual(self.brain.sources([]), [])


class TestScoped(BrainCase):
    def test_other_areas_refused(self):
        a, b = self.source("C01"), self.source("C02", origin_ref="R2")
        self.item(a)
        view = self.brain.scoped(["C01"])
        self.assertIsInstance(view, ScopedBrain)
        self.assertEqual(len(view.brain_items()), 1)
        self.assertEqual(view.get_source(a)["area_id"], "C01")
        for call in (lambda: view.get_source(b), lambda: view.source_lines(b), lambda: view.brain_items(["C02"]),
                     lambda: view.sources(["C02"]), lambda: view.deals("C02"), lambda: view.reviews(["C02"])):
            with self.assertRaises(AreaDenied):
                call()

    def test_library_needs_playbooks_area(self):
        seed_sample(self.brain, self.data)
        with self.assertRaises(AreaDenied):
            self.brain.scoped(["C04"]).playbooks()
        with self.assertRaises(AreaDenied):
            self.brain.scoped(["C04"]).checklist()
        view = self.brain.scoped(["playbooks"])
        self.assertEqual(len(view.playbooks()), 2)
        self.assertEqual(len(view.checklist()), 3)


class TestReviews(BrainCase):
    proposal = {"kind": "requirement", "text": "Hindi screens", "topic": "language-support", "line_from": 2, "line_to": 2,
                "quote_raw": "Reminders on WhatsApp", "quote_clean": "Reminders on WhatsApp"}

    def test_accept_creates_item_with_evidence(self):
        sid = self.source()
        rid = self.brain.queue_review("C01", sid, self.proposal, "low confidence", 0.4, kind="low_confidence")
        self.assertEqual(self.brain.reviews(["C01"])[0]["review_id"], rid)
        item_id = self.brain.decide_review(rid, True, "P05")
        item = self.brain.brain_items(["C01"])[0]
        self.assertEqual((item["item_id"], item["facts"]["confidence"], item["evidence"][0]["source_id"]), (item_id, 0.4, sid))
        self.assertEqual(self.brain.reviews(["C01"]), [])
        self.assertEqual(self.brain.reviews(["C01"], status="accepted")[0]["decided_by"], "P05")
        with self.assertRaises(ValueError):
            self.brain.decide_review(rid, True, "P05")

    def test_reject_creates_nothing(self):
        sid = self.source()
        rid = self.brain.queue_review("C01", sid, self.proposal, "unclear", 0.3, kind="translation")
        self.assertIsNone(self.brain.decide_review(rid, False, "P05"))
        self.assertEqual(self.brain.brain_items(["C01"], state=None), [])
        self.assertEqual(self.brain.reviews(["C01"], status="rejected")[0]["item_id"], None)

    def test_bad_proposal_leaves_review_pending(self):
        sid = self.source()
        rid = self.brain.queue_review("C01", sid, {"kind": "fact"}, "x", 0.2, kind="contradiction")
        with self.assertRaises(ValueError):
            self.brain.decide_review(rid, True, "P05")
        self.assertEqual(len(self.brain.reviews(["C01"])), 1)


class TestReviewRouting(BrainCase):
    def queue(self, sid, area="C01", kind="low_confidence", **kw):
        return self.brain.queue_review(area, sid, TestReviews.proposal, "why", 0.5, kind=kind, **kw)

    def row(self, rid):
        return self.brain.get_review(rid)

    def test_assignee_rule_in_order(self):
        by_hand = self.queue(self.source(received_at="2026-10-19T09:00"), assigned_to="P11")
        submitter = self.queue(self.source(origin_ref="R2", submitted_by="P11"))
        participant = self.queue(self.brain.add_source("C01", "chat", "T", "x", origin_ref="R3", occurred_at=None, language="en",
                                                       participants=[{"name": "", "email": "Ishaan@devx.example"}], lines=lines("a", "b")))
        csm = self.queue(self.source(origin_ref="R4"))
        self.assertEqual([self.row(r)["assigned_to"] for r in (by_hand, submitter, participant, csm)], ["P11", "P11", "P11", "P05"])

    def test_area_owner_from_project_deal_or_admin(self):
        self.mem.ensure_area("C04", kind="client")
        sid = self.source("C04")
        self.assertEqual(self.row(self.queue(sid, "C04"))["assigned_to"], "P01")  # no owner known: first Admin
        self.brain.upsert_deal(deal_id="L20", area_id="C04", owner_id="P03")
        self.assertEqual(self.row(self.queue(sid, "C04"))["assigned_to"], "P03")
        self.brain.upsert_project(project_id="PR05", area_id="C04", name="App", csm_id="P05")
        self.assertEqual(self.row(self.queue(sid, "C04"))["assigned_to"], "P05")  # project CSM first
        sid2 = self.source("C04", origin_ref="R9", deal_id="L20")
        self.assertEqual(self.row(self.queue(sid2, "C04"))["assigned_to"], "P03")  # source names the deal

    def test_unrouted_goes_to_admin(self):
        sid = self.source("hold", submitted_by="P11")
        rid = self.queue(sid, "hold", kind="unrouted")
        self.assertEqual(self.row(rid)["assigned_to"], "P01")
        self.assertEqual(self.row(self.queue(sid, "hold", kind="low_confidence"))["assigned_to"], "P01")

    def test_due_date_and_bad_kind(self):
        rid = self.queue(self.source(received_at="2026-10-19T09:00"))
        self.assertEqual((self.row(rid)["due_on"], self.row(rid)["kind"]), ("2026-10-22", "low_confidence"))
        with self.assertRaises(ValueError):
            self.queue(self.source(origin_ref="R2"), kind="bogus")

    def test_overdue_and_assignee_filter(self):
        old = self.queue(self.source(received_at="2026-10-10T09:00", submitted_by="P11"))
        fresh = self.queue(self.source(origin_ref="R2", received_at="2026-10-19T09:00", submitted_by="P03"))
        by_id = {r["review_id"]: r for r in self.brain.reviews(["C01"])}
        self.assertEqual((by_id[old]["overdue"], by_id[fresh]["overdue"]), (True, False))
        self.assertEqual([r["review_id"] for r in self.brain.reviews(["C01"], assigned_to="P11")], [old])
        self.assertEqual([r["review_id"] for r in self.brain.reviews(["C01"], assigned_to="P03")], [fresh])
        self.assertEqual([r["review_id"] for r in self.brain.reviews(["C01"], assigned_to="P05")], [])
        self.assertEqual([r["review_id"] for r in self.brain.reviews(["C01"], assigned_to="P01")], [old])  # Admin sees overdue
        self.brain.decide_review(old, False, "P11")
        self.assertFalse(self.brain.reviews(["C01"], status="rejected")[0]["overdue"])

    def test_edit_then_accept(self):
        rid = self.queue(self.source())
        item_id = self.brain.decide_review(rid, True, "P05", edited={"text": "Hindi and English screens", "topic": "language-support", "value": "2"})
        item = self.brain.get_brain_item(item_id)
        self.assertEqual((item["text"], item["topic"], item["facts"]["value"]), ("Hindi and English screens", "language-support", "2"))
        row = self.row(rid)
        self.assertEqual((row["edited_by"], row["edited"]["text"], row["status"]), ("P05", "Hindi and English screens", "accepted"))
        self.assertEqual(item["evidence"][0]["quote_raw"], "Reminders on WhatsApp")

    def test_edit_rules(self):
        rid = self.queue(self.source())
        with self.assertRaises(ValueError):
            self.brain.decide_review(rid, True, "P05", edited={"kind": "fact"})
        with self.assertRaises(ValueError):
            self.brain.decide_review(rid, False, "P05", edited={"text": "x"})
        self.assertEqual(self.row(rid)["status"], "pending")

    def test_proposal_rows_do_not_create_items_until_accepted(self):
        sid = self.source(project_id="PR05")
        self.queue(sid)
        self.assertEqual(self.brain.brain_items(["C01"], state=None), [])
        self.brain.decide_review(self.brain.reviews(["C01"])[0]["review_id"], True, "P05")
        self.assertEqual(len(self.brain.brain_items(["C01"])), 1)


class TestUnconfirmedAndContradictions(BrainCase):
    def test_low_confidence_is_stored_at_once_as_unconfirmed(self):
        sid = self.source(project_id="PR05")
        low = self.item(sid, confidence=0.45, project_id="PR05")
        sure = self.item(sid, confidence=0.9, project_id="PR05")
        got = {i["item_id"]: i for i in self.brain.brain_items(["C01"])}  # default state returns both kinds
        self.assertEqual((got[low]["confirmed"], got[low]["state"], got[sure]["confirmed"]), (False, "unconfirmed", True))
        self.assertTrue(got[low]["evidence"])
        self.assertEqual([i["item_id"] for i in self.brain.brain_items(["C01"], state="unconfirmed")], [low])
        self.assertEqual([i["item_id"] for i in self.brain.brain_items(["C01"], state="confirmed")], [sure])
        self.assertEqual((self.brain.unconfirmed_count("C01"), self.brain.unconfirmed_count("C01", project_id="PR05"),
                          self.brain.unconfirmed_count("C01", deal_id="L9")), (1, 1, 0))
        self.assertEqual(self.brain.scoped(["C01"]).unconfirmed_count("C01"), 1)
        with self.assertRaises(AreaDenied):
            self.brain.scoped(["C02"]).unconfirmed_count("C01")

    def test_check_list_row_is_written_and_nothing_blocks(self):
        sid = self.source()
        low = self.item(sid, confidence=0.3)
        untranslated = self.item(sid, confidence=0.9, state="unconfirmed", review_kind="translation")
        rows = {r["item_id"]: r for r in self.brain.reviews(["C01"])}
        self.assertEqual((rows[low]["kind"], rows[untranslated]["kind"]), ("low_confidence", "translation"))
        self.assertEqual(len(self.brain.brain_items(["C01"])), 2)  # both already retrievable

    def test_confirm_and_reject_never_delete(self):
        sid = self.source()
        a, b = self.item(sid, confidence=0.3), self.item(sid, confidence=0.3)
        ra, rb = (next(r["review_id"] for r in self.brain.reviews(["C01"]) if r["item_id"] == i) for i in (a, b))
        self.assertEqual(self.brain.decide_review(ra, True, "P05", edited={"text": "Fixed text"}), a)
        self.assertIsNone(self.brain.decide_review(rb, False, "P05"))
        self.assertEqual((self.brain.get_brain_item(a)["state"], self.brain.get_brain_item(a)["text"]), ("active", "Fixed text"))
        self.assertEqual(self.brain.get_brain_item(b)["state"], "dropped")
        self.assertEqual(self.brain.brain_items(["C01"], state="dropped")[0]["item_id"], b)
        self.assertEqual(self.brain.unconfirmed_count("C01"), 0)

    def test_newer_statement_supersedes_older(self):
        sid = self.source(rows=("Launch is 1 Nov", "Launch moved to 15 Dec"))
        old = self.item(sid, line_from=1, line_to=1, quote_raw="Launch is 1 Nov", said_at="2026-09-01T10:00", topic="launch-date")
        new = self.item(sid, line_from=2, line_to=2, quote_raw="Launch moved to 15 Dec", said_at="2026-10-05T10:00", topic="launch-date")
        out = self.brain.resolve_contradiction(old, new)  # argument order does not matter
        self.assertEqual((out["newer"], out["older"]), (new, old))
        self.assertEqual(self.brain.get_brain_item(old)["state"], "superseded")
        self.assertEqual(self.brain.get_brain_item(new)["state"], "active")
        self.assertEqual([i["item_id"] for i in self.brain.brain_items(["C01"])], [new])
        link = self.mem.links_of(new)[0]
        self.assertEqual((link["from_id"], link["rel"], link["to_id"]), (new, "contradicts", old))
        row = self.brain.get_review(out["review_id"])
        self.assertEqual((row["kind"], row["status"]), ("contradiction", "pending"))
        self.assertEqual(self.brain.resolve_contradiction(new, old)["newer"], new)

    def test_rejecting_a_contradiction_restores_the_older_item(self):
        sid = self.source()
        old = self.item(sid, said_at="2026-09-01T10:00")
        new = self.item(sid, said_at="2026-10-05T10:00")
        rid = self.brain.resolve_contradiction(old, new)["review_id"]
        self.brain.decide_review(rid, False, "P05")
        self.assertEqual((self.brain.get_brain_item(old)["state"], self.brain.get_brain_item(new)["state"]), ("active", "dropped"))

    def test_contradiction_across_areas_refused(self):
        a = self.item(self.source("C01"))
        b = self.item(self.source("C02", origin_ref="R2"), area="C02")
        with self.assertRaises(ValueError):
            self.brain.resolve_contradiction(a, b)


class TestLibraryAndRetrieval(BrainCase):
    def test_save_playbook_replaces_same_deal(self):
        kw = dict(source_area_id="C04", deal_id="L05", client_label="X", industry="healthcare", outcome="won",
                  revenue_inr=1, sections={"a": 1}, tags=["t"], run_id="R1")
        first = self.brain.save_playbook(**kw)
        second = self.brain.save_playbook(**{**kw, "sections": {"a": 2}})
        self.assertEqual(first, second)
        got = self.brain.playbooks()
        self.assertEqual((len(got), got[0]["sections"]), (1, {"a": 2}))
        self.assertEqual(self.brain.playbooks(outcome="lost"), [])

    def test_checklist_by_industry(self):
        self.brain.save_checklist_item(topic="a", question="q1", why="w", learned_from=[], industries=["retail"])
        self.brain.save_checklist_item(topic="b", question="q2", why="w", learned_from=[], industries=[])
        self.assertEqual([c["topic"] for c in self.brain.checklist(industry="healthcare")], ["b"])
        self.assertEqual(len(self.brain.checklist()), 2)

    def test_retrieval_ranking_is_stable(self):
        seed_sample(self.brain, self.data)
        view = self.brain.scoped(["playbooks", "C07"])
        deal = self.brain.deals(["C07"])[0]
        first = similar_deals(view, deal, k=3)
        self.assertEqual(first, similar_deals(view, deal, k=3))
        self.assertEqual([r["area_id"] for r in first], ["C04", "C09"])
        self.assertGreater(first[0]["score"], first[1]["score"])
        self.assertEqual(first[1]["score"], 0.5 + 0.5 * (1 / 4))  # same group; one shared tag of four
        self.assertIn("shared topics", first[0]["why"])

    def test_retrieval_tie_broken_by_deal_id(self):
        for deal_id, area in (("L9", "C02"), ("L3", "C03")):
            self.brain.save_playbook(source_area_id=area, deal_id=deal_id, client_label="x", industry="retail", outcome="won",
                                     revenue_inr=0, sections={}, tags=[], run_id="r")
        view = self.brain.scoped(["playbooks"])
        got = similar_deals(view, {"deal_id": "L50", "area_id": "C08", "industry": "grocery tech", "tags": []})
        self.assertEqual([r["deal_id"] for r in got], ["L3", "L9"])


class TestSimilarShowsEachClientOnce(BrainCase):
    def test_two_closed_deals_of_one_client_show_one_playbook(self):
        for deal, area in (("L1", "C01"), ("L2", "C01"), ("L3", "C04")):
            self.brain.save_playbook(source_area_id=area, deal_id=deal, client_label="A client", industry="retail", outcome="won",
                                     revenue_inr=0, sections={}, tags=["offline-mode"], run_id="r")
        got = similar_deals(self.brain.scoped(["playbooks"]), {"deal_id": "L9", "area_id": "C08", "industry": "retail", "tags": ["offline-mode"]})
        self.assertEqual(sorted(g["area_id"] for g in got), ["C01", "C04"])


class TestEntitiesAndSample(BrainCase):
    def test_projects_deals_revenue(self):
        seed_sample(self.brain, self.data)
        self.assertEqual(self.brain.projects(["C04"])[0]["name"], "Patient Booking App")
        self.assertEqual([d["deal_id"] for d in self.brain.deals(["C07", "C08"], owner_id="P03")], ["L20", "L21"])
        self.assertEqual(self.brain.deals(["C07"], stage="proposal"), [])
        self.assertEqual(self.brain.revenue(["C04"])[0]["amount_inr"], 900000)
        with self.assertRaises(ValueError):
            self.brain.upsert_deal(deal_id="Lx", area_id="C07", bogus=1)

    def test_set_scope_sets_project_and_deal_and_keeps_the_other(self):
        ids = seed_sample(self.brain, self.data)
        item_id = self.brain.brain_items(["C04"])[0]["item_id"]
        self.brain.set_scope(item_id, project_id="PR05")
        self.brain.set_scope(item_id, deal_id="L05")
        facts = self.brain.get_brain_item(item_id)["facts"]
        self.assertEqual((facts["project_id"], facts["deal_id"]), ("PR05", "L05"))
        with self.assertRaises(KeyError):
            self.brain.set_scope("nope", project_id="PR05")
        self.assertTrue(ids)

    def test_every_sample_item_has_evidence(self):
        ids = seed_sample(self.brain, self.data)
        items = [i for area in ("C01", "C04", "C07", "C09") for i in self.brain.brain_items([area])]
        self.assertEqual(len(items), len(ids["items"]))
        self.assertTrue(all(i["evidence"] for i in items))

    def test_memory_reset_clears_brain_tables(self):
        seed_sample(self.brain, self.data)
        self.mem.reset()
        names = {r[0] for r in self.mem.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertFalse([n for n in names if n.startswith("brain_")])


if __name__ == "__main__":
    unittest.main()
