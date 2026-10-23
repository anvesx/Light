"""Tests for the client requests agent: merged duplicates, the daily round, verification, secrets, approvals and the exam."""
import json
import tempfile
import unittest
from dataclasses import replace
from types import SimpleNamespace

from agents.client_requests.fake_brain import brain
from agents.client_requests.replay_exam import run_exam, secret_leaks
from contract.types import Task
from lifecycle_kit.approved_actions import execute_approved
from wiring.build_company_os import build_company_os

MARKER = "Fake-Not-Real-123"


class ClientRequestsCase(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.cos = build_company_os(agents=("client_requests",), state_dir=self._dir.name)

    def round(self, area, day):
        return self.cos.run("client_requests", "system", area, trigger_kind="timer", inputs={"as_of": day})

    def ask(self, who, area, kind, details, day, project="PR02"):
        inputs = {"kind": kind, "project_id": project, "details": details, "as_of": day, "task_id": "T112"}
        return self.cos.run("client_requests", who, area, inputs=inputs)

    def notes(self, person, kind=None):
        return [m for m in self.cos.outbox.messages(person) if kind in (None, m["kind"])]

    def wrap_brain(self, change):
        def wrapped(request):
            reply = brain(request)
            data = json.loads(reply.text)
            change(data)
            return replace(reply, text=json.dumps(data))
        self.cos.gateway._backends["fake"].brains["client_requests"] = wrapped

    def steps(self, result):
        return [s["step"] for s in self.cos.memory.run_steps(result.run_id)]


class DeveloperRequestTests(ClientRequestsCase):
    THEME = "Need theme edit access on tailorbird-menswear.myshopify.com"

    def test_cr1_a_second_ask_is_merged_not_asked_twice(self):
        r = self.ask("P15", "C01", "theme_access", self.THEME, "2026-08-06")
        self.assertEqual(r.status, "done")
        self.assertEqual(self.cos.approvals.pending(), [])
        msg = self.notes("P15", "request_update")[0]
        self.assertIn("RQ033", msg["text"])
        self.assertIn("did not ask the client again", msg["text"])
        items = {i["item_id"]: i["status"] for i in self.cos.memory.items("C01", kinds=["client_request"])}
        self.assertEqual(list(items.values()), ["merged"])
        self.assertEqual([c["subject"] for c in self.cos.memory.cases(area_id="C01", agent="client_requests")],
                         [f"duplicate_ask:{next(iter(items))}"])

    def test_already_granted_is_not_asked_again(self):
        self.ask("P14", "C01", "theme_access", self.THEME, "2026-09-01")
        text = self.notes("P14", "request_update")[0]["text"]
        self.assertIn("already granted on 2026-08-10", text)
        self.assertEqual(self.cos.memory.items("C01", kinds=["client_request"]), [])

    def test_a_different_store_is_a_new_request_and_goes_in_the_next_round(self):
        r = self.ask("P14", "C01", "shopify_collaborator_access",
                     "Add us as collaborator on tailorbird-warehouse.myshopify.com. Thanks", "2026-09-01")
        self.assertEqual(r.status, "done")
        self.assertIn("Logged CRQ-N", self.notes("P14")[0]["text"])
        item = self.cos.memory.items("C01", kinds=["client_request"])[0]
        self.assertEqual(item["status"], "open")
        self.assertEqual(self.cos.approvals.pending(), [])
        nxt = self.round("C01", "2026-09-01")
        self.assertEqual(nxt.status, "held")
        args = self.cos.approvals.pending()[0]["args"]
        self.assertIn(item["item_id"], args["request_ids"])
        self.assertIn("tailorbird-warehouse.myshopify.com", args["text"])
        self.assertEqual(self.cos.memory.get_item(item["item_id"])["status"], "asked")

    def test_project_of_another_client_is_rejected_politely(self):
        r = self.ask("P21", "C04", "theme_access", self.THEME, "2026-09-01", project="PR02")
        self.assertEqual(r.status, "done")
        self.assertIn("not in this client's area", self.notes("P21")[0]["text"])
        self.assertEqual(self.cos.memory.items("C04", kinds=["client_request"]), [])


class KickoffTests(ClientRequestsCase):
    INPUTS = {"sow_id": "SW02-2", "as_of": "2026-06-12"}

    def test_kickoff_lists_everything_from_the_profile_and_waits_for_approval(self):
        r = self.cos.run("client_requests", "P05", "C01", trigger_kind="request", inputs=dict(self.INPUTS))
        self.assertEqual(r.status, "held")
        args = self.cos.approvals.pending()[0]["args"]
        for title in ("Shopify collaborator access", "Theme access", "App install approval", "DNS records",
                      "Content and files", "Decision"):
            self.assertIn(title, args["text"])
        self.assertNotIn("Cloud role", args["text"])
        self.assertEqual(len(args["request_ids"]), 7)
        self.assertEqual(self.notes("P05")[0]["kind"], "kickoff_ready")
        self.assertEqual(self.cos.outbox.messages("X01"), [])
        again = self.cos.run("client_requests", "P05", "C01", trigger_kind="request", inputs=dict(self.INPUTS))
        self.assertEqual(again.status, "done")
        self.assertIn("quiet", self.steps(again))


class DailyRoundTests(ClientRequestsCase):
    def test_cr2_stuck_request_is_escalated_to_the_csm_once(self):
        self.assertEqual(self.notes("P05", "escalation"), [])
        self.round("C04", "2026-10-07")
        self.assertEqual(self.notes("P05", "escalation"), [])
        self.round("C04", "2026-10-08")
        msg = self.notes("P05", "escalation")
        self.assertEqual(len(msg), 1)
        for word in ("RQ044", "9 days", "T290", "Nandini Sethi"):
            self.assertIn(word, msg[0]["text"])
        self.assertEqual(self.cos.memory.get_item("CRQ-RQ044")["status"], "escalated")
        self.round("C04", "2026-10-09")
        self.assertEqual(len(self.notes("P05", "escalation")), 1)

    def test_cr3_granted_but_check_failed_is_reopened_and_both_are_told(self):
        self.round("C02", "2026-09-23")
        self.assertEqual(self.notes("P06", "check_failed"), [])
        self.round("C02", "2026-09-24")
        csm, dev = self.notes("P06", "check_failed"), self.notes("P16", "check_failed")
        self.assertEqual((len(csm), len(dev)), (1, 1))
        self.assertIn("Access denied", csm[0]["text"])
        self.assertIn("RQ042", dev[0]["text"])
        self.assertEqual(self.cos.memory.get_item("CRQ-RQ042")["status"], "reopened")
        self.assertEqual(self.cos.approvals.pending(), [])
        self.round("C02", "2026-09-25")
        self.assertEqual(len(self.notes("P06", "check_failed")), 1)

    def test_a_passed_check_tells_the_developer_once(self):
        self.round("C05", "2026-10-07")
        self.round("C05", "2026-10-08")
        ready = self.notes("P23", "access_ready")
        self.assertEqual(len(ready), 1)
        self.assertIn("RQ047", ready[0]["text"])

    def test_cr4_secret_never_reaches_memory_outbox_approvals_or_steps(self):
        r = self.round("C05", "2026-10-07")
        alert = self.notes("P06", "secret_alert")
        self.assertEqual(len(alert), 1)
        self.assertIn("RQ047", alert[0]["text"])
        self.assertIn("change it now", alert[0]["text"])
        self.assertEqual(secret_leaks(self.cos, [MARKER]), [])
        self.assertEqual([c["subject"] for c in self.cos.memory.cases(area_id="C05")], ["secret_in_chat:RQ047"])
        everything = json.dumps([self.cos.memory.run_steps(r.run_id), self.cos.outbox.messages(),
                                 self.cos.approvals.pending(), self.cos.memory.items("C05"),
                                 self.cos.memory.cases(area_id="C05")])
        self.assertNotIn(MARKER, everything)
        self.assertIn("[secret removed]", json.dumps(self.cos.memory.run_steps(r.run_id)))

    def test_cr1_in_the_round_flags_the_later_duplicate_on_its_day(self):
        self.round("C01", "2026-08-06")
        self.assertEqual(self.notes("P15", "duplicate_merged"), [])
        self.round("C01", "2026-08-07")
        text = self.notes("P15", "duplicate_merged")[0]["text"]
        self.assertIn("RQ034", text)
        self.assertIn("RQ033", text)
        self.assertEqual(self.cos.memory.get_item("CRQ-RQ034")["status"], "merged")
        for ask in self.cos.approvals.pending():
            self.assertNotIn("RQ034", ask["args"]["request_ids"])

    def test_look_alikes_are_not_flagged(self):
        for client, days in (("C01", ("2026-06-17", "2026-06-18", "2026-06-19")),
                             ("C03", ("2026-08-12", "2026-08-14", "2026-08-17"))):
            for day in days:
                self.round(client, day)
        self.assertEqual(self.cos.memory.cases(), [])

    def test_a_quiet_day_makes_no_model_call(self):
        r = self.round("C06", "2026-10-19")
        self.assertEqual(r.status, "done")
        self.assertIn("quiet", self.steps(r))
        self.assertEqual(self.cos.ledger.entries, [])

    def test_one_client_message_per_day_and_no_repeat_on_the_same_day(self):
        self.round("C04", "2026-10-01")
        pending = self.cos.approvals.pending()
        self.assertEqual([p["tool"] for p in pending], ["send_client_message"])
        self.round("C04", "2026-10-01")
        self.assertEqual(len(self.cos.approvals.pending()), 1)
        self.round("C04", "2026-10-02")
        self.assertLessEqual(len(self.cos.approvals.pending()), 2)


class ApprovalTests(ClientRequestsCase):
    def hold_reminder(self):
        r = self.round("C04", "2026-10-01")
        self.assertEqual(r.status, "held")
        return self.cos.approvals.pending()[0]

    def test_client_message_is_held_and_posted_only_after_a_csm_approves(self):
        pending = self.hold_reminder()
        self.assertEqual(pending["tool"], "send_client_message")
        self.assertEqual(pending["args"]["client_contact_id"], "X07")
        self.assertIn("RQ044", pending["args"]["request_ids"])
        self.assertTrue(self.cos.policy.may_approve("csm", "client_requests"))
        self.assertFalse(self.cos.policy.may_approve("engineer", "client_requests"))
        self.assertEqual(self.cos.outbox.messages("X07"), [])
        self.assertEqual(self.cos.memory.items("C04", kinds=["client_ask"])[0]["status"], "proposed")
        self.assertEqual(execute_approved(pending["approval_id"], self.cos.approvals, self.cos.runtime.registry,
                                          self.cos.memory)["status"], "skipped")
        self.cos.approvals.decide(pending["approval_id"], True, "P05")
        done = execute_approved(pending["approval_id"], self.cos.approvals, self.cos.runtime.registry, self.cos.memory)
        self.assertEqual(done["status"], "ran")
        sent = self.cos.outbox.messages("X07")
        self.assertEqual([m["kind"] for m in sent], ["client_message"])
        self.assertIn("do not send passwords", sent[0]["text"].lower())
        self.assertIn("Test or restricted keys only", sent[0]["text"])
        self.assertEqual(self.cos.memory.items("C04", kinds=["client_ask"])[0]["status"], "sent")
        again = execute_approved(pending["approval_id"], self.cos.approvals, self.cos.runtime.registry, self.cos.memory)
        self.assertEqual(again["status"], "skipped")
        self.assertEqual(len(self.cos.outbox.messages("X07")), 1)

    def test_a_rejected_message_is_never_posted(self):
        pending = self.hold_reminder()
        self.cos.approvals.decide(pending["approval_id"], False, "P05")
        execute_approved(pending["approval_id"], self.cos.approvals, self.cos.runtime.registry, self.cos.memory)
        self.assertEqual(self.cos.outbox.messages("X07"), [])

    def test_the_tool_itself_refuses_a_contact_of_another_client(self):
        spec = self.cos.runtime.registry.get("send_client_message")
        self.assertTrue(spec.risky)
        ctx = SimpleNamespace(run_id="r", task=Task("client_requests", "system", "C04", "timer"))
        with self.assertRaises(ValueError):
            spec.fn({"client_contact_id": "X01", "text": "hello", "request_ids": []}, ctx)
        with self.assertRaises(ValueError):
            spec.fn({"client_contact_id": "P05", "text": "hello", "request_ids": []}, ctx)
        with self.assertRaises(ValueError):
            spec.fn({"client_contact_id": "X07", "text": "pw: Abc12345", "request_ids": []}, ctx)
        self.assertEqual(self.cos.outbox.messages(), [])


class RefusalAndCheckTests(ClientRequestsCase):
    def test_a_person_from_another_client_is_refused(self):
        self.assertNotIn("C04", self.cos.directory.client_access("P12"))
        r = self.cos.run("client_requests", "P12", "C04", trigger_kind="request", inputs={"as_of": "2026-10-01"})
        self.assertEqual(r.status, "refused")
        self.assertIn("no access", r.reason)
        r = self.cos.run("client_requests", "X07", "C04", trigger_kind="request", inputs={"as_of": "2026-10-01"})
        self.assertEqual(r.status, "refused")
        self.assertEqual(self.cos.ledger.entries, [])
        self.assertEqual(self.cos.outbox.messages(), [])
        self.assertEqual(self.cos.approvals.pending(), [])

    def test_check_stops_a_client_message_that_asks_for_a_password(self):
        def worse(data):
            data["client_message"]["text"] += "\nPlease send us your password for the portal."
        self.wrap_brain(worse)
        r = self.round("C04", "2026-10-01")
        self.assertEqual(r.status, "failed")
        self.assertIn("password", r.reason)
        self.assertEqual((self.cos.approvals.pending(), self.cos.outbox.messages()), ([], []))

    def test_check_stops_any_text_that_holds_a_secret(self):
        def leak(data):
            data["client_message"]["text"] += "\nOur vault code is pw: Abc12345"
        self.wrap_brain(leak)
        r = self.round("C04", "2026-10-01")
        self.assertEqual((r.status, "holds a secret" in r.reason), ("failed", True))
        self.cos.gateway._backends["fake"].brains["client_requests"] = brain

        def leak_note(data):
            data["notes"][0]["text"] += f" The password was {MARKER}"
        self.wrap_brain(leak_note)
        r = self.round("C05", "2026-10-07")
        self.assertEqual(r.status, "failed")
        self.assertIn("secret", r.reason)
        self.assertEqual(self.cos.outbox.messages(), [])
        self.assertEqual(self.cos.memory.cases(), [])

    def test_check_stops_a_message_to_a_contact_of_another_client(self):
        def wrong_contact(data):
            data["client_message"]["to"] = "X01"
        self.wrap_brain(wrong_contact)
        r = self.round("C04", "2026-10-01")
        self.assertEqual(r.status, "failed")
        self.assertIn("not a contact of this client", r.reason)
        self.assertEqual(self.cos.approvals.pending(), [])

    def test_check_stops_an_unplanned_client_message_and_a_missing_item(self):
        self.wrap_brain(lambda d: d["client_message"].update(text="Hello. Please reply soon."))
        r = self.round("C04", "2026-10-01")
        self.assertEqual(r.status, "failed")
        self.assertIn("leaves out", r.reason)

    def test_check_rejects_a_duplicate_ask_for_something_open_or_granted(self):
        pack = self.cos.packs["client_requests"]
        existing = {"id": "RQ044", "project_id": "PR05", "kind": "api_keys_via_vault", "title": "Clinic API keys",
                    "details": "", "status": "reminded", "stage": "reminded", "created_on": "2026-09-29"}
        granted = dict(existing, id="RQ001", title="Maps API key", status="verified", created_on="2026-06-01")
        ctx = SimpleNamespace(task=Task("client_requests", "system", "C04", "timer"),
                              notes={"cr": {"universe": [existing, granted]}})

        def plan(title):
            item = {"request_id": "CRQ-N0001", "project_id": "PR05", "kind": "api_keys_via_vault", "title": title,
                    "stage": "new_ask", "created_on": "2026-10-19"}
            return {"client_message": {"to": "X07", "items": [item]}, "notes": []}, \
                {"client_message": {"to": "X07", "text": f"Hello {title}", "request_ids": ["CRQ-N0001"]}, "notes": []}
        for title, expect in (("Clinic API keys", "RQ044"), ("Maps API key", "RQ001")):
            understood, decision = plan(title)
            problems = pack.check(ctx, decision, understood)
            self.assertEqual(len(problems), 1, problems)
            self.assertIn(f"duplicate ask: {title!r}", problems[0])
            self.assertIn(expect, problems[0])
        understood, decision = plan("Telematics feed login")
        self.assertEqual(pack.check(ctx, decision, understood), [])


class ExamTests(ClientRequestsCase):
    def test_exam_handles_all_cases_with_no_false_alarm_or_leak(self):
        out = run_exam(self.cos)
        self.assertEqual((out["planted"], out["found"], out["missed"]), (4, 4, 0))
        self.assertEqual(out["handled_correctly"], 4)
        self.assertEqual((out["false_alarms"], out["secret_leaks"]), (0, 0))
        self.assertEqual(out["other_flags"], [])
        self.assertEqual(out["max_lag_days"], 0)
        self.assertTrue(self.cos.memory.scores(exam="client_requests_replay", agent="client_requests"))
        for run in self.cos.memory.runs("client_requests"):
            for step in self.cos.memory.run_steps(run["run_id"]):
                self.assertNotIn(MARKER, json.dumps(step["detail"]))
                self.assertNotIn("[cut:", json.dumps(step["detail"]))
        for ask in self.cos.approvals.pending():
            self.assertEqual(ask["tool"], "send_client_message")
            self.assertEqual(ask["args"]["text"].count("Thank you"), 1)


if __name__ == "__main__":
    unittest.main()
