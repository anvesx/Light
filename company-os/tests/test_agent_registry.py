"""Agent registry: every name imports or is reported missing with a reason, and the builder skips what is missing."""
import unittest

from evaluation.run_all_exams import close_all
from wiring.agent_registry import AGENTS, FAMILIES, available_agents
from wiring.build_company_os import ALL_AGENTS, build_company_os


class RegistryTests(unittest.TestCase):
    def test_every_name_imports_or_has_a_reason(self):
        ok, missing = available_agents()
        self.assertEqual(set(ok) | set(missing), set(AGENTS))
        self.assertFalse(set(ok) & set(missing))
        self.assertTrue(all(isinstance(why, str) and why for why in missing.values()))
        self.assertTrue({"meeting_prep", "finance_watch", "spend_advisor"} <= set(ok))

    def test_families_only_use_registry_names(self):
        self.assertEqual({n for names in FAMILIES.values() for n in names}, set(AGENTS))
        self.assertEqual(ALL_AGENTS, tuple(AGENTS))

    def test_no_list_builds_only_available_agents(self):
        cos = build_company_os()
        try:
            self.assertEqual(set(cos.packs), set(available_agents()[0]))
        finally:
            close_all(cos)

    def test_a_missing_name_is_skipped_not_an_error(self):
        cos = build_company_os(agents=("finance_watch", "no_such_agent"))
        try:
            self.assertEqual(set(cos.packs), {"finance_watch"})
        finally:
            close_all(cos)


if __name__ == "__main__":
    unittest.main()
