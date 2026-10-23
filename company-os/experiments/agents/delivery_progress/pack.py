"""Delivery progress agent pack: real progress against the SOW from git evidence, with private flags to the CSM."""
import json
import re

from connectors.git_tools import git_tools
from connectors.tool_reply import days_between
from contract.types import ToolCall
from lifecycle_kit.action_tools import make_send_private_message
from lifecycle_kit.agent_pack import AgentPack

UNBILLED_PRS, REWORK_REVISIONS = 3, 4
BEHIND_MIN_ELAPSED, BEHIND_RATIO, AT_RISK_RATIO, LATE_DAYS = 0.30, 0.6, 0.8, 14
COOLDOWN_DAYS = 7
THRESHOLDS = {"unbilled_prs": UNBILLED_PRS, "rework_revisions": REWORK_REVISIONS,
              "behind_min_elapsed_pct": int(BEHIND_MIN_ELAPSED * 100), "behind_ratio": BEHIND_RATIO}
SEVERITIES = ("low", "medium", "high")
PROMPT_MARK = "PROGRESS_JSON:\n"
ID_RE = re.compile(r"\b(?:PR|SI|PL|GR|DP|CASE|[PXSC])\d{1,6}(?:-\d+)?\b")
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
NUM_RE = re.compile(r"\d+(?:\.\d+)?")
SYSTEM = ("You help a CSM (a DevX project manager) see real delivery progress against the signed SOW. Use only the "
          "numbers, ids and dates in the data you are given. Write short, plain, non-technical English. Never "
          "measure, compare or name individual developers, and never give PR counts or lines per person. "
          "Never mention PRs, pull requests, merges, commits, branches or PR titles: describe the work in plain "
          "business words (features, scope items, tasks, how much of the planned work is done).")


class DeliveryProgressPack(AgentPack):
    name = "delivery_progress"
    starter_roles = frozenset({"csm", "project_lead", "ceo", "rnd_lead", "system"})
    approver_roles = frozenset({"csm", "ceo"})

    def __init__(self, parts):
        self.parts = parts

    def tools(self):
        return [*git_tools(self.parts.data_conn), make_send_private_message(self.parts.outbox)]

    def system_prompt(self):
        return SYSTEM

    # record: reads only through the checked tool path; a PR-merge event narrows the run to that PR's project
    def record(self, ctx):
        pr_id = ctx.task.inputs.get("pr_id")
        burn = _read(ctx, "scope_burndown", {"pr_id": pr_id} if pr_id else {})
        trigger = burn.get("trigger_pr")
        narrow = {"project_id": trigger["project_id"]} if trigger else {}
        return {"burn": burn, "trigger": trigger, "pace": _read(ctx, "project_pace", narrow),
                "unlinked": _read(ctx, "unlinked_merged_prs", {**narrow, "limit": 100})}

    # understand: every status and signal is computed here, with fixed thresholds
    def understand(self, ctx, rec):
        as_of, area = rec["burn"]["as_of"], ctx.task.area_id
        scopes = {p["project_id"]: p["scope"] for p in rec["burn"]["projects"]}
        projects, signals, snapshots = [], [], {}
        for pace in rec["pace"]["projects"]:
            pid = pace["project_id"]
            snap, sigs = _project_snapshot(pace, scopes.get(pid, []), rec["unlinked"], as_of, area, rec["trigger"])
            snapshots[pid] = snap
            signals += sigs
            projects.append({k: snap[k] for k in ("project_id", "project_name", "status", "pace", "scope_counts")})
        if not projects:
            return {"quiet": True}
        for p in projects:
            p["flags_now"] = [{"signal": s["signal"], "scope_item_id": s.get("scope_item_id")}
                              for s in signals if s["project_id"] == p["project_id"]]
        for snap in snapshots.values():
            snap["flags"] = [{"signal": s["signal"], "scope_item_id": s.get("scope_item_id"),
                              "severity": s["severity_hint"]} for s in signals if s["project_id"] == snap["project_id"]]
        new = [s for s in signals if not self._recent(area, s, as_of)]
        ctx.notes["dp"] = {"as_of": as_of, "snapshots": snapshots,
                           "by_key": {_key(s["signal"], s["project_id"], s.get("scope_item_id")): s for s in new}}
        return {"as_of": as_of, "client_id": area, "thresholds": THRESHOLDS, "projects": projects, "signals": new}

    def _recent(self, area, sig, as_of):
        """True when the same flag was raised in the last COOLDOWN_DAYS days (no daily repeats)."""
        subject = _subject(sig["signal"], sig["project_id"], sig.get("scope_item_id"))
        for c in self.parts.memory.cases(area_id=area, agent=self.name):
            if c["subject"] != subject:
                continue
            then = json.loads(c["evidence"]).get("as_of")
            if then and 0 <= days_between(as_of, then) < COOLDOWN_DAYS:
                return True
        return False

    def decision_prompt(self, understood):
        return ("Below is today's delivery progress for one client. Write one headline per project (one plain "
                "sentence on how it stands against the SOW). For each signal write a flag: the evidence in numbers, "
                "why it matters, and a suggested next step. Do not name or count people. Reply with final JSON only: "
                '{"headlines": [{"project_id", "headline"}], "flags": [{"signal", "project_id", "scope_item_id" '
                '(only for scope_rework), "severity" (low|medium|high), "evidence", "why_it_matters", '
                '"next_step"}]}.\n' + PROMPT_MARK + json.dumps(understood, indent=1))

    def parse_decision(self, final_text):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", final_text.strip())
        data = json.loads(text)
        if not isinstance(data.get("flags"), list) or not isinstance(data.get("headlines"), list):
            raise ValueError("need a headlines list and a flags list")
        return data

    # check: nothing reaches a person or memory unless it matches the code's findings
    def check(self, ctx, decision, understood):
        problems, blob = [], json.dumps(understood)
        known_ids, known_dates = set(ID_RE.findall(blob)), set(DATE_RE.findall(blob))
        known_nums = {float(n) for n in NUM_RE.findall(DATE_RE.sub("", ID_RE.sub("", blob)))}
        names = _devx_names(self.parts.data_conn)
        by_key = ctx.notes["dp"]["by_key"]
        seen = set()

        def text_ok(tag, text):
            out = _check_text(tag, text, known_ids, known_dates, known_nums)
            return out + [f"{tag}: names a person ({n})" for n in names if n in text]

        for i, f in enumerate(decision["flags"]):
            tag = f"flag {i + 1}"
            key = _key(f.get("signal"), f.get("project_id"), f.get("scope_item_id"))
            sig = by_key.get(key)
            if sig is None or key in seen:
                problems.append(f"{tag}: no matching new signal for {key}")
                continue
            seen.add(key)
            if f.get("severity") not in SEVERITIES:
                problems.append(f"{tag}: bad severity {f.get('severity')!r}")
            for field in ("evidence", "why_it_matters", "next_step"):
                if not isinstance(f.get(field), str) or not f[field].strip():
                    problems.append(f"{tag}: missing {field}")
                else:
                    problems += text_ok(f"{tag} {field}", f[field])
            d = self.parts.directory
            if not (d.is_devx(sig["csm_id"]) and d.role(sig["csm_id"]) == "csm"):
                problems.append(f"{tag}: recipient {sig['csm_id']!r} is not a DevX CSM")
        if seen != set(by_key):
            problems.append(f"missing flags for: {sorted(set(by_key) - seen)}")
        heads = {h.get("project_id"): h.get("headline") for h in decision["headlines"]}
        if set(heads) != {p["project_id"] for p in understood["projects"]}:
            problems.append("headlines must cover each project exactly once")
        for pid, text in heads.items():
            problems += text_ok(f"headline {pid}", str(text or ""))
        return problems

    # act: one private message per CSM
    def act(self, ctx, decision):
        by_key, per_csm = ctx.notes["dp"]["by_key"], {}
        for f in decision["flags"]:
            sig = by_key[_key(f["signal"], f["project_id"], f.get("scope_item_id"))]
            per_csm.setdefault(sig["csm_id"], []).append((f, sig))
        return [ToolCall(f"msg-{csm}", "send_private_message",
                         {"to_person_id": csm, "text": _message(items), "kind": "flag"})
                for csm, items in sorted(per_csm.items())]

    def remember(self, ctx, decision, acted):
        dp, area = ctx.notes["dp"], ctx.task.area_id
        heads = {h["project_id"]: h["headline"] for h in decision["headlines"]}
        snaps = []
        for pid, snap in sorted(dp["snapshots"].items()):
            snap = {**snap, "headline": heads.get(pid)}
            snaps.append(self.parts.memory.add_item(
                area, kind="progress_snapshot", text=json.dumps(snap, sort_keys=True), topic=pid,
                source="delivery_progress", source_ref=ctx.run_id, created_at=dp["as_of"]))
        cases = []
        for f in decision["flags"]:
            sig = dp["by_key"][_key(f["signal"], f["project_id"], f.get("scope_item_id"))]
            evidence = {"as_of": dp["as_of"], "project_id": f["project_id"], "scope_item_id": f.get("scope_item_id"),
                        "text": f["evidence"], "why_it_matters": f["why_it_matters"], "next_step": f["next_step"],
                        "facts": sig["facts"]}
            cases.append(self.parts.memory.add_case(
                ctx.run_id, self.name, area, _subject(f["signal"], f["project_id"], f.get("scope_item_id")),
                f["severity"], evidence))
        return {"snapshots": snaps, "cases": cases, "flags": len(decision["flags"])}


def make_pack(parts) -> DeliveryProgressPack:
    return DeliveryProgressPack(parts)


def _read(ctx, name, args):
    out = ctx.notes["invoke_tool"](name, args)
    if out["verdict"] != "allow":
        raise RuntimeError(f"read {name} not allowed: {out['result']}")
    data = json.loads(out["result"])
    if "error" in data:
        raise RuntimeError(f"read {name} failed: {data['error']}")
    return data


def _key(signal, project_id, scope_item_id):
    return (signal, project_id, scope_item_id or None)


def _subject(signal, project_id, scope_item_id):
    return f"{signal}:{project_id}" + (f":{scope_item_id}" if scope_item_id else "")


def _scope_status(it, as_of):
    started = it["tasks_done"] or it["prs_merged"] or it["prs_open"]
    if it["tasks_done"] and not it["tasks_open"] and it["prs_merged"] and not it["prs_open"] and it["in_prod"]:
        return "done"
    if it["due_on"] and it["due_on"] < as_of:
        return "at risk"
    return "in progress" if started else "not started"


def _project_snapshot(pace, scope, unlinked, as_of, area, trigger):
    pid = pace["project_id"]
    base = {"project_id": pid, "project_name": pace["name"], "csm_id": pace["csm_id"], "lead_id": pace["lead_id"]}
    items = [{"id": it["id"], "title": it["title"], "status": _scope_status(it, as_of), "est": it["est"],
              "tasks_done": it["tasks_done"], "tasks_open": it["tasks_open"], "prs_merged": it["prs_merged"],
              "last_merge": it["last_merge"], "in_prod": it["in_prod"], "revisions": it["revisions"]} for it in scope]
    counts = {s: sum(1 for i in items if i["status"] == s) for s in ("not started", "in progress", "done", "at risk")}
    counts["total"] = len(items)
    e, m = pace["elapsed_share"], pace["merged_share"]
    behind = e >= BEHIND_MIN_ELAPSED and m < BEHIND_RATIO * e
    signals = []
    unbilled = [p for p in unlinked["prs"] if p["project_id"] == pid and not p["chore"]]
    if len(unbilled) >= UNBILLED_PRS:
        n = len(unbilled)
        signals.append({**base, "signal": "unbilled_work", "severity_hint": "high" if n >= 5 else "medium",
                        "facts": {"unbilled_prs": n, "first_merged_on": unbilled[0]["merged_on"],
                                  "last_merged_on": unbilled[-1]["merged_on"],
                                  "prs": [{"pr_id": p["pr_id"], "title": p["title"], "merged_on": p["merged_on"]}
                                          for p in unbilled[:6]]}})
    for it in items:
        if it["revisions"] >= REWORK_REVISIONS:
            signals.append({**base, "signal": "scope_rework", "scope_item_id": it["id"],
                            "severity_hint": "high" if it["revisions"] >= 6 else "medium",
                            "facts": {"scope_item": it["title"], "revisions_after_client_meetings": it["revisions"],
                                      "estimate_hours": it["est"]}})
    pace_facts = {"elapsed_pct": round(100 * e, 1), "merged_pct": round(100 * m, 1),
                  "planned_end_on": pace["planned_end_on"], "projected_finish": pace["projected_finish"],
                  "days_late": pace["days_late"], "pace_date": pace["pace_date"]}
    if behind:
        signals.append({**base, "signal": "behind_deadline",
                        "severity_hint": "high" if (pace["days_late"] or 999) >= 60 else "medium",
                        "facts": pace_facts})
    risky = (e >= BEHIND_MIN_ELAPSED and m < AT_RISK_RATIO * e) or (pace["days_late"] or 0) > LATE_DAYS \
        or any(s["signal"] == "scope_rework" for s in signals)
    status = "behind" if behind else ("at risk" if risky else "on track")
    snap = {**base, "client_id": area, "as_of": as_of, "status": status, "pace": pace_facts, "scope": items,
            "scope_counts": counts, "unbilled_prs": len(unbilled)}
    if trigger and trigger["project_id"] == pid:
        snap["trigger_pr_id"] = trigger["pr_id"]
    return snap, signals


def _devx_names(conn):
    return sorted(r[0] for r in conn.execute("SELECT name FROM people WHERE is_devx = 1"))


# CSMs read business words only; code-level words in a letter mean the model leaked internals.
CODE_WORDS = re.compile(r"\bPRs?\b|pull request|\bmerged?\b|\bcommits?\b|\bbranch(es)?\b|\b(feat|fix|chore|refactor):", re.I)


def _check_text(tag, text, known_ids, known_dates, known_nums):
    problems = []
    if CODE_WORDS.search(text):
        problems.append(f"{tag}: uses code words ({CODE_WORDS.search(text).group(0)}); write plain business words")
    for i in set(ID_RE.findall(text)) - known_ids:
        problems.append(f"{tag}: id {i} is not in the data")
    for dt in set(DATE_RE.findall(text)) - known_dates:
        problems.append(f"{tag}: date {dt} is not in the data")
    for n in set(NUM_RE.findall(DATE_RE.sub("", ID_RE.sub("", text)))):
        if float(n) not in known_nums:
            problems.append(f"{tag}: number {n} is not in the data")
    return problems


def _message(items):
    lines = ["Delivery progress flags for your projects:"]
    for f, sig in items:
        lines.append(f"\n[{f['severity'].upper()}] {sig['project_name']} ({f['project_id']})\n"
                     f"What we see: {f['evidence']}\nWhy it matters: {f['why_it_matters']}\n"
                     f"Suggested next step: {f['next_step']}")
    return "\n".join(lines)
