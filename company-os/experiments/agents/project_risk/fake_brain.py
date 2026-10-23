"""Deterministic stand-in for the model: reads the signals JSON and writes plain-English flags."""
import json

from contract.types import ModelReply

MARK = "SIGNALS_JSON:\n"


def brain(request):
    content = request.messages[-1]["content"]
    data = json.loads(content[content.index(MARK) + len(MARK):])
    flags, followups = [], []
    for s in data["signals"]:
        evidence, why, step = _WRITERS[s["signal"]](s, s["facts"])
        flag = {"signal": s["signal"], "project_id": s["project_id"], "severity": s["severity_hint"],
                "evidence": evidence, "why_it_matters": why, "next_step": step}
        if s.get("person_id"):
            flag["person_id"] = s["person_id"]
        flags.append(flag)
        if s["severity_hint"] == "high":
            followups.append({"title": f"{_TITLES[s['signal']]} on {s['project_id']}", "owner_id": s["csm_id"]})
    return ModelReply(text=json.dumps({"flags": flags, "followups": followups}))


def _hours(s, f):
    return (f"{f['hours_logged']} hours are logged against {f['estimate_hours']} hours in the signed scope "
            f"({f['logged_pct']}%), and {f['tasks_open']} of {f['tasks_total']} tasks ({f['open_task_pct']}%) are still open.",
            f"The team has used more than the agreed hours ({f['hours_over_estimate']} over) and a lot of work is left, "
            "so the project may lose money or need a new scope talk.",
            "Check what is left with the project lead, then agree with the client whether to cut scope or raise the estimate.")


def _silent(s, f):
    return (f"The client has not written in the shared channel for {f['days_silent']} days "
            f"(last message on {f['last_client_message_on']}).",
            "A quiet client on a live project often means feedback or approvals are stuck, or the client is unhappy.",
            "Call or message the client contact this week and ask if anything blocks them.")


def _overdue(s, f):
    old = f" The oldest was due on {f['oldest_due_on']}." if "oldest_due_on" in f else ""
    return (f"{f['overdue_tasks']} tasks are past their due date, out of {f['tasks_open']} open tasks.{old}",
            "Late tasks pile up and push the delivery date.",
            "Go through the late tasks with the project lead and set new dates, or move people to the blocked ones.")


def _overload(s, f):
    w = ", ".join(str(h) for h in f["weekly_hours"])
    return (f"One person on this project logged {w} hours in the last {f['weeks_in_a_row']} weeks "
            f"(from {f['first_week_start']} to {f['last_week_end']}), every week above 55.",
            "Long hours for many weeks raise the risk of mistakes, burnout and a sudden exit.",
            "Talk to the person and the project lead about lowering the load. Check the full workload in the existing DevX console.")


def _change(s, f):
    left = f"only {f['hours_left']} hours are left" if f["hours_left"] else "no hours are left"
    return (f"A SOW change that is not yet accepted adds {f['unaccepted_change_hours']} hours, but {left} "
            f"of {f['estimate_hours']}.",
            "If the team starts this work before it is accepted, the hours may go unpaid.",
            "Ask the client to accept the change in writing before work starts on it.")


_WRITERS = {"hours_over_sow": _hours, "client_silent": _silent, "overdue_tasks": _overdue,
            "overloaded_engineer": _overload, "sow_change_exceeds_remaining": _change}
_TITLES = {"hours_over_sow": "Review hours against the SOW", "client_silent": "Reach out to the quiet client",
           "overdue_tasks": "Re-plan the overdue tasks", "overloaded_engineer": "Review one person's workload",
           "sow_change_exceeds_remaining": "Get the SOW change accepted"}
