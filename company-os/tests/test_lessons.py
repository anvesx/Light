"""Lessons: a failed check leaves a candidate in the runtime store, a person promotes it, experience.md reaches the prompt."""
import tempfile
import unittest
from pathlib import Path

from lifecycle_kit import agent_folder
from lifecycle_kit.agent_folder import MAX_LESSONS, build_system_prompt
from lifecycle_kit.lessons import LessonLog, promote_candidate
from lifecycle_kit.lifecycle_runner import LifecycleRunner
from tests.test_guardrails import World, task

REPO = Path(__file__).resolve().parent.parent


class FailedCheckTests(unittest.TestCase):
    def setUp(self):
        self.w = World(self)
        self.w.memory.add_item("C01", "note", "Client likes Fridays", status="open")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.log = LessonLog(tmp.name)
        self.runner = LifecycleRunner(self.w.runtime, self.log)

    def test_failed_check_writes_one_candidate_per_problem(self):
        self.w.pack.problems = ["total is wrong", "name is shown"]
        r = self.runner.run(self.w.pack, task())
        self.assertEqual(r.status, "failed")
        rows = self.log.candidates()
        self.assertEqual([c["problem"] for c in rows], ["total is wrong", "name is shown"])
        self.assertEqual({(c["agent"], c["run_id"], c["signal"]) for c in rows}, {("tiny", r.run_id, "failed check")})

    def test_a_pass_writes_nothing(self):
        r = self.runner.run(self.w.pack, task())
        self.assertEqual(r.status, "done")
        self.assertEqual(self.log.candidates(status=None), [])
        self.assertFalse(self.log.path.exists())

    def test_no_log_means_no_candidates(self):
        self.w.pack.problems = ["bad"]
        self.assertEqual(LifecycleRunner(self.w.runtime).run(self.w.pack, task()).status, "failed")

    def test_the_log_is_outside_the_source_tree(self):
        self.assertNotIn(REPO, self.log.path.resolve().parents)

    def test_built_company_os_keeps_candidates_in_its_state_dir(self):
        from wiring.build_company_os import build_company_os
        from evaluation.run_all_exams import close_all
        cos = build_company_os(agents=("finance_watch",), seed_brain=False)
        self.addCleanup(close_all, cos)
        self.assertTrue(str(cos.runner.lessons.path).startswith(cos.state_dir))
        self.assertNotIn(REPO, cos.runner.lessons.path.resolve().parents)


class PromoteTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        (self.dir / "agent").mkdir()
        self.folder = self.dir / "agent"
        (self.folder / "experience.md").write_text("# Experience\n\nNo lessons yet.\n")
        self.log = LessonLog(self.dir / "data")
        self.log.record_failed_check("tiny", "R1", ["the total is wrong"])

    def test_promote_adds_the_lesson_and_closes_the_candidate(self):
        promote_candidate(self.log, "R1-1", "Check every total before you write it.", self.folder)
        self.assertIn("- Check every total before you write it.", (self.folder / "experience.md").read_text())
        self.assertEqual(self.log.candidates(), [])
        self.assertEqual(self.log.candidates(status="promoted")[0]["status"], "promoted")

    def test_promote_refuses_unknown_candidate_or_empty_text(self):
        with self.assertRaises(ValueError):
            promote_candidate(self.log, "R9-1", "x", self.folder)
        with self.assertRaises(ValueError):
            promote_candidate(self.log, "R1-1", "  ", self.folder)
        self.assertEqual(len(self.log.candidates()), 1)


class PromptLessonTests(unittest.TestCase):
    def folder(self, lessons):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name)
        (folder / "instructions.md").write_text("You are a test.\n")
        (folder / "guardrails.md").write_text("# Guardrails\n\n- Never lie.\n")
        (folder / "experience.md").write_text("# Experience\n\nNotes that are not lessons.\n\n" + "".join(f"- {x}\n" for x in lessons))
        return folder

    def test_lessons_reach_the_prompt(self):
        prompt = build_system_prompt(self.folder(["Round up."]))
        self.assertEqual(prompt, "You are a test.\n\nNever do these things:\n- Never lie.\n\nLessons from past runs:\n- Round up.")

    def test_no_lessons_adds_no_section(self):
        self.assertNotIn("Lessons", build_system_prompt(self.folder([])))

    def test_at_most_20_lessons_and_the_newest_win(self):
        lessons = [f"lesson {n}" for n in range(1, 26)]
        prompt = build_system_prompt(self.folder(lessons))
        self.assertEqual(prompt.count("- lesson "), MAX_LESSONS)
        self.assertIn("- lesson 25", prompt)
        self.assertNotIn("- lesson 5\n", prompt + "\n")
        self.assertEqual(len(agent_folder.approved_lessons(self.folder(lessons))), 20)


if __name__ == "__main__":
    unittest.main()
