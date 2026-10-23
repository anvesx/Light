"""Deterministic stand-in for the model: reads the plan JSON and writes the messages in plain English."""
import json

from contract.types import ModelReply

from .request_playbooks import NEVER_LINE

MARK = "PLAN_JSON:\n"


def brain(request):
    content = request.messages[-1]["content"]
    plan = json.loads(content[content.index(MARK) + len(MARK):])
    cm = plan.get("client_message")
    out = {"client_message": _client_message(plan, cm) if cm else None,
           "notes": [{"to": n["to"], "topic": n["topic"], "text": _WRITERS[n["topic"]](n["facts"])}
                     for n in plan["notes"]]}
    return ModelReply(text=json.dumps(out))


def _client_message(plan, cm):
    projects = sorted({i["project_name"] for i in cm["items"]})
    where = " and ".join(projects)
    if plan["mode"] == "kickoff":
        intro = (f"Welcome to the {where} project. DevX needs a few things from you to start well. "
                 "If you do them now, we will not need to ask again later.")
    else:
        intro = f"This is our one message for today about {where}. Here is what we still need from you."
    lines = [f"Hello {cm['to_name']},", "", intro, ""]
    for n, item in enumerate(cm["items"], 1):
        tail = {"reminder_1": f" (a friendly reminder, first asked on {item['first_asked_on']})",
                "reminder_2": f" (second reminder, first asked on {item['first_asked_on']}; our team is waiting on it)"
                }.get(item["stage"], "")
        lines += [f"{n}. {item['title']}{tail}", f"   What we need: {item['ask']}", "   Steps:"]
        lines += [f"   - {s}" for s in item["steps"]]
        lines += [f"   Access level: {item['least_privilege']}", ""]
    lines += [NEVER_LINE, "If anything is unclear, reply here and your DevX project manager will help.", "",
              "Thank you,", "The DevX team"]
    return {"to": cm["to"], "text": "\n".join(lines), "request_ids": [i["request_id"] for i in cm["items"]]}


def _escalation(f):
    blocked = (f"It blocks task {', '.join(f['blocked_tasks'])}. " if f["blocked_tasks"] else "")
    return (f"Escalation: {f['title']} ({f['request_id']}) on {f['project_name']} ({f['project_id']}) has waited "
            f"{f['days_open']} days for the client, after {f['reminders_sent']} reminder{'' if f['reminders_sent'] == 1 else 's'}. {blocked}"
            f"Tasks on this project have waited {f['project_days_waited_on_client']} days in total on the client. "
            f"Next step: call {f['contact_name']} today, or ask your account manager to step in.")


def _check_failed(f):
    tail = ("Please ask the client to fix it, then ask the developer to check again." if f["audience"] == "csm" else
            "The CSM has been told. Please do not ask the client again yourself.")
    return (f"The client says {f['title']} ({f['request_id']}) is granted, but the access check failed on "
            f"{f['checked_on']} ({f['target']}): {f['detail']} The request is open again. {tail}")


def _secret(f):
    return (f"A client contact ({f['contact_name']}) put a password or key in the client Slack channel, in the reply "
            f"to {f['title']} ({f['request_id']}) on project {f['project_id']}. This agent did not copy it anywhere. "
            "Please ask the client to change it now, delete the message, and share any new secret only through the vault.")


def _duplicate(f):
    return (f"Your request {f['duplicate_id']} ({f['title']}) is the same as {f['original_id']}, asked on "
            f"{f['original_created_on']} by {f['original_requested_by_name']}. I merged them, so the client is not asked "
            "twice. You will hear from me when access is granted and checked.")


def _ready(f):
    names = "; ".join(f"{r['title']} ({r['request_id']})" for r in f["requests"])
    return f"Access is granted and checked for you: {names}. You can use it now."


def _request_update(f):
    o = f["outcome"]
    if o == "rejected":
        return f"I could not log your {f['kind']} request: {f['reason']}."
    if o == "new":
        return (f"Logged {f['request_id']}: {f['title']}. It goes to {f['contact_name']} in the next daily message "
                f"to the client. Tasks on this project have waited {f['project_days_waited_on_client']} days on the client so far.")
    if o == "duplicate":
        return (f"This is already asked as {f['request_id']} ({f['title']}) on {f['asked_on']}, and it is still open. "
                "I did not ask the client again. You will hear when it is granted and checked.")
    if o == "already_granted":
        return (f"{f['request_id']} ({f['title']}) was already granted on {f['granted_on'] or f['asked_on']} and checked. "
                "I did not ask the client again.")
    return (f"{f['request_id']} ({f['title']}) was granted but the access check failed, so it is open again. "
            "The CSM knows. I did not ask the client again.")


def _kickoff(f):
    return (f"The kickoff checklist for {f['project_name']} ({f['project_id']}) is ready: {f['request_count']} items "
            f"({', '.join(f['titles'])}). The client message waits for your approval. Once sent, most asks happen only once.")


_WRITERS = {"escalation": _escalation, "check_failed": _check_failed, "secret_alert": _secret,
            "duplicate_merged": _duplicate, "access_ready": _ready, "request_update": _request_update,
            "kickoff_ready": _kickoff}
