"""Tests for the client request read tools: area guard, as_of dates, secret redaction and the playbooks."""
import json
import unittest

from agents.client_requests.request_playbooks import PLAYBOOKS, kickoff_kinds
from agents.client_requests.secret_redaction import asks_for_password, find_secrets, has_secret, mask, mask_all
from company_data import DB_PATH, connect
from connectors.client_request_tools import client_request_tools
from contract.types import RunContext, Task

MARKER = "Fake-Not-Real-123"


class ToolCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = connect(DB_PATH)
        cls.tools = {t.name: t for t in client_request_tools(cls.conn)}

    def call(self, name, area, args=None, as_of="2026-10-19"):
        task = Task(agent="client_requests", caller_id="system", area_id=area, trigger_kind="test",
                    inputs={"as_of": as_of})
        out = self.tools[name].fn(args or {}, RunContext(run_id="r", task=task, memory=None))
        return json.loads(out)


class AreaGuardTests(ToolCase):
    def test_every_tool_refuses_a_non_client_area(self):
        for name in self.tools:
            out = self.call(name, "devx-internal")
            self.assertIn("is not available for area", out["error"], name)

    def test_project_of_another_client_is_refused(self):
        for name in ("open_client_requests", "access_check_results", "client_contacts_for", "project_profile"):
            self.assertIn("not in area", self.call(name, "C02", {"project_id": "PR05"})["error"], name)

    def test_area_argument_must_match_the_task(self):
        self.assertIn("not the task's area", self.call("open_client_requests", "C04", {"client_id": "C01"})["error"])

    def test_rows_come_only_from_the_task_area(self):
        rows = self.call("open_client_requests", "C04", {"state": "all", "limit": 60})["requests"]
        self.assertTrue(rows)
        self.assertEqual({r["project_id"] for r in rows}, {"PR05"})
        profile = self.call("project_profile", "C04")["projects"]
        self.assertEqual([p["project_id"] for p in profile], ["PR05"])

    def test_outside_text_flag(self):
        self.assertTrue(self.tools["open_client_requests"].reads_outside_text)
        self.assertFalse(self.tools["client_contacts_for"].reads_outside_text)
        self.assertFalse(any(t.risky for t in self.tools.values()))


class AsOfTests(ToolCase):
    def test_future_requests_and_events_are_hidden(self):
        before = self.call("open_client_requests", "C04", {"state": "all", "limit": 60}, as_of="2026-09-28")["requests"]
        self.assertNotIn("RQ044", {r["request_id"] for r in before})
        after = self.call("open_client_requests", "C04", {}, as_of="2026-10-08")["requests"]
        row = next(r for r in after if r["request_id"] == "RQ044")
        self.assertEqual((row["days_open"], row["reminders_sent"], row["status"]), (9, 2, "reminded"))
        self.assertEqual(row["blocked_tasks"][0]["task_id"], "T290")
        self.assertTrue(row["blocked_tasks"][0]["still_blocked"])
        early = self.call("open_client_requests", "C04", {}, as_of="2026-10-01")["requests"]
        row = next(r for r in early if r["request_id"] == "RQ044")
        self.assertEqual((row["days_open"], row["reminders_sent"]), (2, 0))

    def test_status_comes_from_events_not_from_the_final_column(self):
        def status(day):
            rows = self.call("open_client_requests", "C02", {"state": "all", "limit": 60}, as_of=day)["requests"]
            return next(r["status"] for r in rows if r["request_id"] == "RQ042")
        self.assertEqual(status("2026-09-22"), "asked")
        self.assertEqual(status("2026-09-23"), "granted")
        self.assertEqual(status("2026-09-24"), "failed_verification")

    def test_access_checks_are_hidden_before_their_date(self):
        self.assertEqual(self.call("access_check_results", "C02", as_of="2026-09-23")["checks"], [])
        check = self.call("access_check_results", "C02", as_of="2026-09-24")["checks"][0]
        self.assertEqual((check["request_id"], check["result"]), ("RQ042", "fail"))

    def test_blocked_days_grow_with_the_date(self):
        def days(day):
            return self.call("project_profile", "C04", as_of=day)["projects"][0]["blocked_days"]
        self.assertGreater(days("2026-10-19")["task_days_waited_on_client"], days("2026-10-08")["task_days_waited_on_client"])
        self.assertEqual(days("2026-10-19")["tasks_blocked_now"], 1)

    def test_bad_date_is_an_error(self):
        self.assertIn("as_of", self.call("open_client_requests", "C04", as_of="19-10-2026")["error"])


class RedactionTests(ToolCase):
    def test_tool_masks_the_pasted_password(self):
        text = self.tools["open_client_requests"].fn(
            {"recent_days": 5}, RunContext("r", Task("client_requests", "system", "C05", "test",
                                                      inputs={"as_of": "2026-10-07"}), None))
        self.assertNotIn(MARKER, text)
        row = json.loads(text)["requests"][0]
        self.assertEqual(row["request_id"], "RQ047")
        self.assertTrue(row["secret_in_chat"])
        reply = next(e["text"] for e in row["events"] if e["kind"] == "client_reply")
        self.assertIn("[secret removed]", reply)

    def test_no_tool_output_on_any_day_holds_the_marker_or_gets_cut(self):
        for area in ("C01", "C02", "C03", "C04", "C05", "C06"):
            for day in ("2026-08-07", "2026-09-24", "2026-10-07", "2026-10-19"):
                for name, args in (("open_client_requests", {"recent_days": 5}), ("access_check_results", {}),
                                   ("project_profile", {}), ("client_contacts_for", {})):
                    out = self.tools[name].fn(args, RunContext("r", Task("client_requests", "system", area, "test",
                                                                          inputs={"as_of": day}), None))
                    self.assertNotIn(MARKER, out)
                    self.assertLess(len(out), 6000)

    def test_contacts_show_names_and_roles_only(self):
        out = self.call("client_contacts_for", "C04", {"project_id": "PR05"})
        self.assertEqual(out["suggested_owner"], "X07")
        for c in out["contacts"]:
            self.assertEqual(set(c), {"person_id", "name", "role", "requests_handled"})

    def test_mask_and_find(self):
        text = "Telematics login pw: Fake-Not-Real-123 and the key is in the portal page."
        self.assertEqual(find_secrets(text), [MARKER])
        self.assertNotIn(MARKER, mask(text))
        for secret_text in ("password is hunter2", "api key: abcd1234", "token=abc12345", "use sk_live_abcdefgh12345",
                            "AKIAABCDEFGHIJKLMNOP", "ghp_abcdefghijklmnopqrstuvwx", "aB3dE6gH9jK2mN5pQ8sT1vW4xY7z"):
            self.assertTrue(has_secret(secret_text), secret_text)
            self.assertIn("[secret removed]", mask(secret_text))
        self.assertEqual(mask_all({"a": [text, 3]})["a"][1], 3)
        self.assertNotIn(MARKER, json.dumps(mask_all({"a": [text]})))

    def test_normal_text_is_not_a_secret(self):
        for text in ("The API key is shown once", "Please add the keys to the vault link we sent.",
                     "tailorbird-menswear.myshopify.com on 2026-10-07T13:05", "Keys are in the vault link now.",
                     "Do not send keys in chat or email."):
            self.assertFalse(has_secret(text), text)

    def test_password_ask_is_found_but_the_warning_is_fine(self):
        self.assertTrue(asks_for_password("Please send us your password."))
        self.assertTrue(asks_for_password("Share the pw for the portal"))
        self.assertFalse(asks_for_password("Please do not send passwords or keys in chat or email."))
        self.assertFalse(asks_for_password("Sign in through your own account instead of sharing a password."))

    def test_playbooks_are_safe_and_complete(self):
        self.assertEqual(set(PLAYBOOKS), {"shopify_collaborator_access", "theme_access", "app_install_approval",
                                          "dns_record", "cloud_role", "api_keys_via_vault", "content_assets", "decision"})
        for kind, pb in PLAYBOOKS.items():
            text = " ".join([pb["ask"], *pb["steps"], pb["least_privilege"], pb["check"]])
            self.assertFalse(has_secret(text), kind)
            self.assertFalse(asks_for_password(text), kind)
            self.assertTrue(pb["steps"] and pb["least_privilege"], kind)
        self.assertIn("dns_record", kickoff_kinds("shopify", True, False))
        self.assertNotIn("cloud_role", kickoff_kinds("shopify", True, False))
        self.assertIn("cloud_role", kickoff_kinds("mobile", False, True))
        self.assertNotIn("theme_access", kickoff_kinds("web", True, True))


if __name__ == "__main__":
    unittest.main()
