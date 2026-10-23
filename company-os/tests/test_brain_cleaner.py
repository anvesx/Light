"""Cleaner agent: clean English lines, untranslated lines kept raw, raw never changed, area check on its tools."""
import unittest

from control_plane.company_brain import extract_rules
from control_plane.company_brain.write_tools import make_save_clean_lines, untranslated_lines
from contract.types import RunContext, Task
from evaluation.run_all_exams import close_all

from tests.brain_test_support import make_cos, receive_ref


class CleanerRulesTests(unittest.TestCase):
    def test_filler_is_removed_from_english(self):
        self.assertEqual(extract_rules.remove_filler("Um, we need, you know, UPI payment"), "we need, UPI payment")

    def test_speaker_is_matched_to_a_participant(self):
        people = [{"name": "Anthony Fernandes"}, {"name": "Nandini Sethi"}]
        self.assertEqual(extract_rules.fix_speaker("anthony", people), "Anthony Fernandes")
        self.assertEqual(extract_rules.fix_speaker("Unknown Person", people), "Unknown Person")


class CleanerAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cos = make_cos()
        cls.sid = receive_ref(cls.cos, "SRC13")["source_id"]   # one line has no translation in the fixture
        cls.before = [l["text"] for l in cls.cos.brain.source_lines(cls.sid)]
        cls.result = cls.cos.run("brain_cleaner", "system", "C04", trigger_kind="event", inputs={"source_id": cls.sid})

    @classmethod
    def tearDownClass(cls):
        close_all(cls.cos)

    def test_every_line_has_clean_text_and_raw_is_unchanged(self):
        self.assertEqual(self.result.status, "done")
        lines = self.cos.brain.source_lines(self.sid)
        self.assertEqual([l["text"] for l in lines], self.before)
        self.assertTrue(all(l["clean_text"] for l in lines))
        self.assertEqual(self.cos.brain.get_source(self.sid)["status"], "cleaned")

    def test_an_untranslated_line_keeps_raw_text_and_gets_a_review_row(self):
        source = self.cos.brain.get_source(self.sid)
        gaps = untranslated_lines(self.cos.brain, source)
        self.assertEqual(gaps, [5])
        line = self.cos.brain.source_lines(self.sid)[4]
        self.assertEqual(line["clean_text"], line["text"])
        self.assertEqual(self.cos.brain.reviews(["C04"])[0]["kind"], "translation")

    def test_translated_line_uses_the_translation(self):
        self.assertIn("insurance claim", self.cos.brain.source_lines(self.sid)[1]["clean_text"])

    def test_a_second_run_does_nothing(self):
        again = self.cos.run("brain_cleaner", "system", "C04", trigger_kind="event", inputs={"source_id": self.sid})
        self.assertEqual(again.final_text, "quiet")

    def test_a_source_of_another_area_is_refused(self):
        ctx = RunContext("R0", Task("brain_cleaner", "system", "C01", "event"), None)
        with self.assertRaises(ValueError):
            make_save_clean_lines(self.cos.brain).fn({"source_id": self.sid, "lines": []}, ctx)

    def test_a_run_in_another_area_cannot_read_the_source(self):
        other = self.cos.run("brain_cleaner", "system", "C01", trigger_kind="event", inputs={"source_id": self.sid})
        self.assertEqual(other.final_text, "quiet")
        self.assertEqual(self.cos.brain.get_source(self.sid)["area_id"], "C04")


if __name__ == "__main__":
    unittest.main()
