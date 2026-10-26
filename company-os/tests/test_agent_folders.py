"""Every registered agent has a complete, correct agent folder, and its prompt comes from instructions.md."""
import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from evaluation.run_all_exams import close_all
from lifecycle_kit import agent_folder
from lifecycle_kit.agent_folder import LIFECYCLE_STEPS, REQUIRED_FILES, check_agent_folder, parse_frontmatter
from lifecycle_kit.agent_pack import AgentPack
from wiring.agent_registry import AGENTS, FAMILIES
from wiring.build_company_os import build_company_os


def folder_of(name):
    return Path(importlib.import_module(AGENTS[name]).__file__).resolve().parent


class AgentFolderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cos = build_company_os(seed_brain=False)
        cls.addClassCleanup(close_all, cls.cos)

    def test_every_registered_agent_has_all_files(self):
        self.assertEqual(set(self.cos.packs), set(AGENTS))
        for name in AGENTS:
            for file in REQUIRED_FILES:
                self.assertTrue((folder_of(name) / file).is_file(), f"{name} has no {file}")

    def test_folder_is_correct_for_each_agent(self):
        for name in AGENTS:
            self.assertEqual(check_agent_folder(folder_of(name), name, self.cos.packs[name]), [], name)

    def test_agent_md_matches_registry_and_pack(self):
        for name, pack in self.cos.packs.items():
            meta = agent_folder.read_agent_md(folder_of(name))
            self.assertEqual(meta["name"], name)
            self.assertTrue(meta["description"].strip())
            self.assertEqual(meta["tools"], [s.name for s in pack.tools()])
            self.assertEqual(set(meta["starter_roles"]), set(pack.starter_roles))
            self.assertEqual(set(meta["approver_roles"]), set(pack.approver_roles))
            self.assertEqual(meta["reads_library"], pack.reads_library)
            self.assertIn(name, FAMILIES[meta["family"]])

    def test_graph_steps_follow_the_lifecycle_order(self):
        for name in AGENTS:
            graph = json.loads((folder_of(name) / "graph.json").read_text())
            self.assertEqual([s["step"] for s in graph["steps"]], list(LIFECYCLE_STEPS), name)

    def test_prompt_is_instructions_then_guardrails(self):
        for name, pack in self.cos.packs.items():
            instructions = (folder_of(name) / "instructions.md").read_text().strip()
            prompt = pack.system_prompt()
            self.assertTrue(prompt.startswith(instructions), name)
            self.assertIn("Never do these things:", prompt)
            self.assertNotIn("Lessons from past runs", prompt)   # experience.md starts with no lessons

    def test_no_pack_keeps_its_prompt_in_code(self):
        for name in AGENTS:
            source = (folder_of(name) / "pack.py").read_text()
            self.assertNotIn("def system_prompt", source, name)
            self.assertNotIn("SYSTEM = ", source, name)


class CheckerTests(unittest.TestCase):
    def make_folder(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name)
        src = folder_of("finance_watch")
        for file in REQUIRED_FILES:
            (folder / file).write_text((src / file).read_text())
        return folder

    def test_a_good_copy_has_no_problems(self):
        self.assertEqual(check_agent_folder(self.make_folder(), "finance_watch"), [])

    def test_missing_file_and_wrong_name_are_found(self):
        folder = self.make_folder()
        self.assertTrue(any("does not match" in p for p in check_agent_folder(folder, "other")))
        (folder / "memory.md").unlink()
        self.assertEqual(check_agent_folder(folder, "finance_watch"), ["missing memory.md"])

    def test_bad_graph_and_empty_description_are_found(self):
        folder = self.make_folder()
        graph = json.loads((folder / "graph.json").read_text())
        graph["steps"].reverse()
        (folder / "graph.json").write_text(json.dumps(graph))
        lines = (folder / "agent.md").read_text().split("\n")
        (folder / "agent.md").write_text("\n".join("description:" if l.startswith("description:") else l for l in lines))
        problems = check_agent_folder(folder, "finance_watch")
        self.assertTrue(any("graph.json steps" in p for p in problems))
        self.assertIn("agent.md description is empty", problems)

    def test_frontmatter_parser(self):
        meta, body = parse_frontmatter('---\nname: x\ndescription: One: two.\ntools: [a, b]\nempty: []\nflag: true\n---\n\nBody\n')
        self.assertEqual(meta, {"name": "x", "description": "One: two.", "tools": ["a", "b"], "empty": [], "flag": True})
        self.assertEqual(body, "Body")

    def test_a_pack_outside_an_agent_folder_has_an_empty_prompt(self):
        class Loose(AgentPack):
            pass
        self.assertEqual(Loose().system_prompt(), "")

    def test_default_prompt_reads_the_folder(self):
        folder = self.make_folder()
        (folder / "instructions.md").write_text("You are a test.\n")

        class P(AgentPack):
            pass
        with mock.patch.object(agent_folder, "pack_folder", return_value=folder):
            prompt = P().system_prompt()
        self.assertTrue(prompt.startswith("You are a test.\n\nNever do these things:\n- "))


if __name__ == "__main__":
    unittest.main()
