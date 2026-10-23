"""Deterministic stand-in for the model: reads the progress JSON and writes headlines and plain-English flags."""
import json
import re

from contract.types import ModelReply

MARK = "PROGRESS_JSON:\n"


def brain(request):
    content = request.messages[-1]["content"]
    data = json.loads(content[content.index(MARK) + len(MARK):])
    heads = [{"project_id": p["project_id"], "headline": _headline(p)} for p in data["projects"]]
    flags = []
    for s in data["signals"]:
        evidence, why, step = _WRITERS[s["signal"]](s["facts"])
        flag = {"signal": s["signal"], "project_id": s["project_id"], "severity": s["severity_hint"],
                "evidence": evidence, "why_it_matters": why, "next_step": step}
        if s.get("scope_item_id"):
            flag["scope_item_id"] = s["scope_item_id"]
        flags.append(flag)
    return ModelReply(text=json.dumps({"headlines": heads, "flags": flags}))


def _headline(p):
    pace, c = p["pace"], p["scope_counts"]
    return (f"{p['project_name']} is {p['status']}: about {pace['merged_pct']}% of the planned work is done after "
            f"{pace['elapsed_pct']}% of the time, and {c['done']} of {c['total']} scope items are finished.")


def plain_feature(title):
    """A code title in business words: 'feat: T0123 gift wrapping option' -> 'gift wrapping option'."""
    t = re.sub(r"^\s*(feat|fix|chore|refactor|docs|test)(\([^)]*\))?:\s*", "", title, flags=re.I)
    return re.sub(r"\bT\d{3,}[-\s]*", "", t).strip(" -")


def _unbilled(f):
    features = [plain_feature(p["title"]) for p in f["prs"]]
    listed = ", ".join(features[:-1]) + (" and " if len(features) > 1 else "") + features[-1]
    return (f"{f['unbilled_prs']} things were built that are not in the signed scope, between {f['first_merged_on']} "
            f"and {f['last_merged_on']}: {listed}.",
            "Work outside the signed scope is being built and may go unbilled.",
            "Ask the project lead what these are, then decide with the client whether to raise a SOW change.")


def _rework(f):
    return (f"The scope item '{f['scope_item']}' was changed {f['revisions_after_client_meetings']} times after "
            f"client meetings (estimate {f['estimate_hours']} hours).",
            "Repeated rework on one item eats hours that the SOW did not plan for.",
            "Agree the exact wanted result with the client in writing before the next change.")


def _behind(f):
    if f["projected_finish"]:
        pace = (f"At this pace the project finishes on {f['projected_finish']}, {f['days_late']} days after the "
                f"planned end on {f['planned_end_on']}.")
    else:
        pace = f"No planned work is finished yet, and the planned end is {f['planned_end_on']}."
    return (f"{f['elapsed_pct']}% of the time is used but only about {f['merged_pct']}% of the planned work is done. "
            + pace,
            "The planned end will be missed unless the pace or the plan changes.",
            "Review the plan with the project lead and tell the client early if the date must move.")


_WRITERS = {"unbilled_work": _unbilled, "scope_rework": _rework, "behind_deadline": _behind}
