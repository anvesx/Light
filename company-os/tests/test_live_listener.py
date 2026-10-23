"""Tests for the live listener: pure code checks on a line, with a small hand-made brain."""
import unittest

from agents.meeting_prep.live_copilot.listener import LiveListener, values_in
from control_plane.company_brain.topic_lexicon import load_lexicon

DECISION = {"item_id": "I1", "kind": "decision", "topic": "reminders", "text": "We decided: the reminders will go by WhatsApp only.",
            "source_id": "SRC-1", "origin_ref": "SRC25", "source_kind": "fathom", "occurred_at": "2026-09-30T05:30", "line_from": 14}
OPEN = {"item_id": "I2", "kind": "question", "topic": "data-residency", "text": "Where is the data stored?", "source_id": "SRC-2",
        "origin_ref": "SRC19", "line_from": 6}
CHECK = [{"checklist_id": "CK1", "topic": "insurance-claims", "question": "Do patients claim insurance?", "why": "late once", "learned_from": ["C04"]},
         {"checklist_id": "CK2", "topic": "training", "question": "Who trains the staff?", "why": "late once", "learned_from": []}]


def line(n, text, speaker="X1", **kw):
    return {"line_no": n, "t_sec": n * 10, "speaker": "S", "speaker_id": speaker, "lang": "en", "text": text, **kw}


def make(**kw):
    return LiveListener(load_lexicon(), kw.get("checklist", CHECK), kw.get("open", [OPEN]), kw.get("decisions", [DECISION]), None)


class ListenerTests(unittest.TestCase):
    def test_values(self):
        v = values_in("Launch on 6 November, budget 40 lakh, by SMS")
        self.assertEqual((v["date"], v["amount"], v["channel"]), ({"6 nov"}, {"40 lakh"}, {"sms"}))

    def test_gap_from_checklist_and_open_item(self):
        lis = make()
        s = lis.hear(line(1, "Many patients have insurance."))[0]
        self.assertEqual((s["kind"], s["topic"]), ("gap", "insurance-claims"))
        self.assertEqual(s["cites"][0]["checklist_id"], "CK1")
        s2 = lis.hear(line(2, "Where will the data be stored?"))[0]
        self.assertEqual(s2["topic"], "data-residency")
        self.assertEqual(s2["cites"][0]["origin_ref"], "SRC19")

    def test_contradiction_cites_the_decision(self):
        s = make().hear(line(1, "We will send reminders by SMS instead."))[0]
        self.assertEqual(s["kind"], "contradiction")
        self.assertIn("On Sep 30 in a call you agreed", s["text"])
        self.assertEqual(s["cites"][0]["line_no"], 14)

    def test_same_value_is_not_a_contradiction(self):
        self.assertEqual(make(checklist=[], open=[]).hear(line(1, "WhatsApp reminders are fine.")), [])

    def test_date_and_amount_contradiction(self):
        d = {**DECISION, "topic": "launch-date", "text": "We decided the launch is on 6 November."}
        s = make(decisions=[d]).hear(line(1, "Can the launch be 20 November?"))[0]
        self.assertEqual(s["kind"], "contradiction")

    def test_one_suggestion_per_topic_and_per_line(self):
        lis = make()
        self.assertEqual(len(lis.hear(line(1, "insurance and training both matter"))), 1)
        self.assertEqual(lis.hear(line(2, "insurance again")), [])

    def test_asked_topic_is_no_gap(self):
        lis = make()
        lis.hear(line(1, "Do you handle insurance claims?", speaker="P03"))
        self.assertEqual(lis.hear(line(2, "Yes, insurance is needed.")), [])

    def test_our_own_line_gets_no_suggestion(self):
        self.assertEqual(make().hear(line(1, "Let us talk about insurance.", speaker="P03")), [])

    def test_unasked_checklist_item_near_the_end(self):
        lis = LiveListener(load_lexicon(), CHECK, [], [], None, total_lines=10)
        self.assertEqual(lis.hear(line(2, "hello")), [])
        s = lis.hear(line(9, "Shall we sign next week?"))[0]
        self.assertEqual(s["kind"], "follow_up")
        self.assertEqual(s["topic"], "insurance-claims")
        self.assertIn("training", s["text"])

    def test_hinglish_line_uses_translation_file(self):
        lis = LiveListener(load_lexicon(), CHECK, [], [], {"LCX:1": "Our patients have insurance."}, call_id="LCX")
        s = lis.hear(line(1, "Hamare patients insurance wale hain", lang="hinglish"))[0]
        self.assertEqual(s["topic"], "insurance-claims")
        self.assertEqual(lis.clean_text(line(1, "x", lang="hinglish")), "Our patients have insurance.")


if __name__ == "__main__":
    unittest.main()
