"""Client requests agent pack: asks the client once, reminds politely, verifies access and keeps secrets out."""
import json
import re

from connectors.client_request_tools import client_request_tools
from connectors.tool_reply import days_between
from contract.types import ToolCall, ToolSpec
from lifecycle_kit.action_tools import make_send_private_message
from lifecycle_kit.agent_pack import AgentPack

from .request_playbooks import KINDS, kickoff_kinds, playbook_for
from .secret_redaction import asks_for_password, has_secret, mask, mask_all

NAME, SOURCE = "client_requests", "agent:client_requests"
DUPLICATE_WINDOW_DAYS, STUCK_DAYS, NOTICE_DAYS = 5, 9, 3
MARK = "PLAN_JSON:\n"
OPEN_STATES = ("open", "asked", "reminded")
SEVERITY = {"duplicate_ask": "low", "request_stuck": "high", "granted_check_failed": "high", "secret_in_chat": "high"}
SYSTEM = ("You write short, plain, polite messages for DevX's client requests. Use only the facts and steps in the plan. "
          "Always ask for delegated, least-privilege access. Never ask for a password and never write a secret.")
STOP = {"for", "the", "to", "a", "on", "of", "and", "access", "need", "please", "in", "with", "our", "we", "an", "is"}
HOST_RE = re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)+\b", re.I)


def make_send_client_message(parts) -> ToolSpec:
    """Risky tool: it waits for a person's approval. After approval it posts to the outbox as a client message."""
    def fn(args, ctx):
        contact, text = args["client_contact_id"], args["text"]
        person = parts.directory.get(contact)
        if not person or person["is_devx"] or person["client_id"] != ctx.task.area_id:
            raise ValueError(f"{contact!r} is not a contact of client {ctx.task.area_id!r}")
        if has_secret(text) or asks_for_password(text):
            raise ValueError("the message holds a secret or asks for a password")
        msg_id = parts.outbox.post(contact, text, run_id=ctx.run_id, agent=ctx.task.agent, kind="client_message")
        for rid in args.get("request_ids", []):
            for ask in parts.memory.items(ctx.task.area_id, kinds=["client_ask"], topic=rid, status="proposed"):
                parts.memory.set_item_status(ask["item_id"], "sent")
        return f"sent {msg_id}"
    return ToolSpec(
        name="send_client_message",
        description="Send one message to a contact on the client side. Always waits for a person's approval.",
        params={"type": "object", "required": ["client_contact_id", "text", "request_ids"], "properties": {
            "client_contact_id": {"type": "string"}, "text": {"type": "string"},
            "request_ids": {"type": "array", "items": {"type": "string"}}}},
        fn=fn, risky=True)


class ClientRequestsPack(AgentPack):
    name = NAME
    starter_roles = frozenset({"engineer", "designer", "project_lead", "csm", "ceo", "rnd_lead", "system"})
    approver_roles = frozenset({"csm", "ceo"})

    def __init__(self, parts):
        self.parts = parts

    def tools(self):
        return [*client_request_tools(self.parts.data_conn), make_send_private_message(self.parts.outbox),
                make_send_client_message(self.parts)]

    def system_prompt(self):
        return SYSTEM

    # record: every read goes through the checked tool path
    def record(self, ctx):
        read = lambda name, args=None: _read(ctx, name, args or {})
        inputs = ctx.task.inputs
        as_of = inputs.get("as_of") or self.parts.clock.today
        inputs["as_of"] = as_of
        mode = "kickoff" if inputs.get("sow_id") else "request" if inputs.get("kind") else "round"
        rec = {"mode": mode, "as_of": as_of, "memory": self._memory_state(ctx)}
        try:
            if mode == "round":
                rec["requests"] = read("open_client_requests", {"recent_days": DUPLICATE_WINDOW_DAYS})["requests"]
                rec["checks"] = read("access_check_results", {"days": 14})["checks"]
                rec["projects"] = read("project_profile")["projects"]
            elif mode == "request":
                pid = inputs.get("project_id")
                rec["projects"] = read("project_profile", {"project_id": pid})["projects"]
                rec["requests"] = read("open_client_requests", {"project_id": pid, "kind": inputs["kind"],
                                                                "state": "all", "events": False})["requests"]
            else:
                rec["projects"] = read("project_profile", {"sow_id": inputs["sow_id"]})["projects"]
                pid = rec["projects"][0]["project_id"] if rec["projects"] else None
                rec["requests"] = (read("open_client_requests", {"project_id": pid, "state": "all", "events": False})
                                   ["requests"] if pid else [])
            args = {k: inputs[k] for k in ("project_id", "kind") if inputs.get(k)}
            rec["contacts"] = read("client_contacts_for", args)
        except RuntimeError as e:
            if mode == "round":
                raise
            rec["error"] = str(e)
        return rec

    def _memory_state(self, ctx):
        area = ctx.task.area_id
        items = ctx.memory.items(area, kinds=["client_request", "client_ask", "client_notice"])
        asks = {}
        for i in items:
            if i["kind"] == "client_ask":
                asks.setdefault(i["topic"], []).append({"text": i["text"], "created_on": i["created_at"][:10],
                                                        "status": i["status"]})
        return {"requests": {i["item_id"]: i for i in items if i["kind"] == "client_request"}, "asks": asks,
                "told": {i["topic"] for i in items if i["kind"] == "client_notice"},
                "subjects": {c["subject"] for c in self.parts.memory.cases(area_id=area, agent=NAME)}}

    # understand: every finding is computed here from fixed rules; the model only writes the words
    def understand(self, ctx, rec):
        ctx.notes["cr"] = {"universe": [], "requests": [], "cases": [], "client_items": [], "told": [], "blocked_days": {}}
        plan = {"round": self._round, "request": self._request, "kickoff": self._kickoff}[rec["mode"]](ctx, rec)
        if not plan or plan.get("quiet") or not (plan.get("client_message") or plan["notes"]):
            return {"quiet": True}
        return {"mode": rec["mode"], "as_of": rec["as_of"], "client_id": ctx.task.area_id, **plan}

    # -- the daily round
    def _round(self, ctx, rec):
        cr, area, mem = ctx.notes["cr"], ctx.task.area_id, rec["memory"]
        projects = {p["project_id"]: p for p in rec["projects"]}
        rows = [_from_table(r, mem["asks"]) for r in rec["requests"]]
        made = [_from_item(i, mem["asks"]) for i in mem["requests"].values()
                if i["item_id"].startswith("CRQ-N") and i["status"] in OPEN_STATES]
        for r in made:
            r["days_open"] = days_between(rec["as_of"], r["created_on"])
        universe = cr["universe"] = rows + made
        for r in rows:
            r["stage"] = {"failed_verification": "reopened"}.get(r["status"], r["status"])
            known = mem["requests"].get(f"CRQ-{r['id']}", {}).get("status")
            if known == "merged" or (known == "escalated" and r["status"] in OPEN_STATES):
                r["stage"] = known
        notes = (self._duplicates(cr, mem, universe) + self._secrets(cr, mem, rows, projects, area)
                 + self._stuck(cr, mem, universe, projects, area) + self._verification(cr, mem, rec, universe, projects, area))
        batch = []
        for r in sorted(universe, key=lambda x: (x["created_on"], x["id"])):
            p = projects.get(r["project_id"])
            if r["closed"] or r["stage"] not in OPEN_STATES or (p and p["status"] != "active"):
                continue
            stage = _due_stage(r, rec["as_of"])
            if stage:
                batch.append(self._item(r, stage, p))
        cr["requests"] += [r for r in universe if r not in cr["requests"]]
        cr["blocked_days"] = {p["project_id"]: p["blocked_days"] for p in rec["projects"]}
        if not batch and not notes:
            return {"quiet": True}
        return {"client_message": self._client_plan(cr, rec, batch), "notes": notes}

    def _duplicates(self, cr, mem, universe):
        notes = []
        for later, earlier in _duplicate_pairs([r for r in universe if r["status"] != "cancelled"]):
            subject = f"duplicate_ask:{later['id']}"
            if later["closed"] or later["stage"] == "merged" or subject in mem["subjects"]:
                continue
            later["stage"] = "merged"
            cr["cases"].append(_case(subject, "duplicate_ask", later, {"duplicate_of": earlier["id"]}))
            notes.append(_note(later["requested_by"], "duplicate_merged", [later["id"], earlier["id"]], {
                "title": later["title"], "duplicate_id": later["id"], "original_id": earlier["id"],
                "original_created_on": earlier["created_on"],
                "original_requested_by_name": self._name(earlier["requested_by"])}))
        return notes

    def _secrets(self, cr, mem, rows, projects, area):
        notes = []
        for r in rows:
            subject = f"secret_in_chat:{r['id']}"
            if r["secret"] and subject not in mem["subjects"]:
                cr["cases"].append(_case(subject, "secret_in_chat", r, {"secret_masked": True}))
                notes.append(_note(self._csm(projects, r, area), "secret_alert", [r["id"]], {
                    "title": r["title"], "request_id": r["id"], "project_id": r["project_id"],
                    "contact_name": self._name(r["owner"]) if r["owner"] else "a client contact"}))
        return notes

    def _stuck(self, cr, mem, universe, projects, area):
        notes = []
        for r in universe:
            subject, p = f"request_stuck:{r['id']}", projects.get(r["project_id"])
            if r["closed"] or r["stage"] not in OPEN_STATES or r["escalated"] or subject in mem["subjects"]:
                continue
            if (r["days_open"] or 0) >= STUCK_DAYS and r["reminders"] >= 1:
                r["stage"] = "escalated"
                cr["cases"].append(_case(subject, "request_stuck", r, {"days_open": r["days_open"]}))
                notes.append(_note(self._csm(projects, r, area), "escalation", [r["id"]], {
                    "title": r["title"], "request_id": r["id"], "project_id": r["project_id"],
                    "project_name": p["name"] if p else r["project_id"], "days_open": r["days_open"],
                    "reminders_sent": r["reminders_told"],
                    "blocked_tasks": [b["task_id"] for b in r["blocked_tasks"] if b["still_blocked"]],
                    "project_days_waited_on_client": p["blocked_days"]["task_days_waited_on_client"] if p else 0,
                    "contact_name": self._name(r["owner"]) if r["owner"] else "the client contact"}))
        return notes

    def _verification(self, cr, mem, rec, universe, projects, area):
        notes, ready, by_id = [], {}, {r["id"]: r for r in universe}
        for c in rec["checks"]:
            row = by_id.get(c["request_id"]) or _from_check(c)
            if row["id"] not in by_id:
                cr["requests"].append(row)
            subject = f"granted_check_failed:{row['id']}"
            keep = row.get("stage") == "merged"
            if c["result"] == "fail":
                row["stage"] = "merged" if keep else "reopened"
                if subject in mem["subjects"]:
                    continue
                cr["cases"].append(_case(subject, "granted_check_failed", row,
                                         {"checked_at": c["checked_at"], "detail": c["detail"]}))
                facts = {"title": row["title"], "request_id": row["id"], "project_id": row["project_id"],
                         "checked_on": c["checked_at"][:10], "target": c["target"], "detail": c["detail"]}
                for to, audience in ((self._csm(projects, row, area), "csm"), (row["requested_by"], "developer")):
                    notes.append(_note(to, "check_failed", [row["id"]], {**facts, "audience": audience}))
            else:
                row["stage"] = "merged" if keep else "verified"
                if row["id"] not in mem["told"] and days_between(rec["as_of"], c["checked_at"]) <= NOTICE_DAYS:
                    ready.setdefault(row["requested_by"], []).append(row)
                    cr["told"].append(row["id"])
        for dev, items in sorted(ready.items()):
            notes.append(_note(dev, "access_ready", [i["id"] for i in items],
                               {"requests": [{"request_id": i["id"], "title": i["title"]} for i in items]}))
        return notes

    # -- one request from a developer
    def _request(self, ctx, rec):
        cr, inputs, as_of = ctx.notes["cr"], ctx.task.inputs, rec["as_of"]
        kind, pid = inputs["kind"], inputs.get("project_id")
        profile = (rec.get("projects") or [None])[0]
        who = self._developer(ctx, profile)
        base = {"kind": kind, "project_id": pid}
        if rec.get("error") or profile is None or kind not in KINDS:
            reason = "this kind of request is not known" if kind not in KINDS else "this project is not in this client's area"
            return {"client_message": None, "notes": [_note(who, "request_update", [], {
                **base, "outcome": "rejected", "reason": reason})]}
        details = mask(str(inputs.get("details") or "")).strip()
        title = re.split(r"(?<=[.!?])\s", details)[0].rstrip(".!?")[:80]
        title = title if len(title) >= 3 else playbook_for(kind)["title"]
        mem = rec["memory"]
        existing = [_from_table(r, mem["asks"]) for r in rec["requests"] if r["status"] != "cancelled"]
        for i in mem["requests"].values():
            data = json.loads(i["text"])
            if i["item_id"].startswith("CRQ-N") and i["status"] in OPEN_STATES \
                    and (data["project_id"], data["kind"]) == (pid, kind):
                existing.append(_from_item(i, mem["asks"]))
        cr["universe"] = existing
        new_id = self._new_ids(1)[0]
        row = {"id": new_id, "source": "memory", "project_id": pid, "kind": kind, "title": title, "details": details,
               "requested_by": who, "owner": None, "task_id": inputs.get("task_id"), "created_on": as_of,
               "stage": "open", "status": "open", "closed": False}
        match = next((e for e in existing if _same_target(_text_of(e), f"{title} {details}")), None)
        if match:
            outcome = ("check_failed" if match["status"] == "failed_verification" else
                       "already_granted" if match["closed"] else "duplicate")
            if outcome == "duplicate":
                row["stage"] = "merged"
                cr["requests"].append(row)
                cr["cases"].append(_case(f"duplicate_ask:{new_id}", "duplicate_ask", row, {"duplicate_of": match["id"]}))
            facts = {**base, "outcome": outcome, "request_id": match["id"], "title": match["title"],
                     "status": match["status"], "asked_on": match["first_asked"] or match["created_on"],
                     "granted_on": match.get("granted_on")}
            return {"client_message": None, "notes": [_note(who, "request_update", [match["id"]], facts)]}
        row["owner"] = self._owner(rec, None)
        cr["requests"].append(row)
        facts = {**base, "outcome": "new", "request_id": new_id, "title": title,
                 "contact_name": self._name(row["owner"]) if row["owner"] else "the client contact",
                 "project_days_waited_on_client": profile["blocked_days"]["task_days_waited_on_client"]}
        return {"client_message": None, "notes": [_note(who, "request_update", [new_id], facts)]}

    # -- the kickoff checklist
    def _kickoff(self, ctx, rec):
        cr, as_of = ctx.notes["cr"], rec["as_of"]
        if not rec.get("projects") or rec.get("error"):
            return {"quiet": True}
        p, mem = rec["projects"][0], rec["memory"]
        cr["universe"] = [_from_table(r, mem["asks"]) for r in rec["requests"]]
        have = {r["kind"] for r in cr["universe"] if r["status"] != "cancelled"}
        for i in mem["requests"].values():
            data = json.loads(i["text"])
            if i["item_id"].startswith("CRQ-N") and i["status"] != "cancelled" and data["project_id"] == p["project_id"]:
                have.add(data["kind"])
        kinds = [k for k in kickoff_kinds(p["platform"], p["uses_client_domain"], p["uses_client_cloud"]) if k not in have]
        if not kinds:
            return {"quiet": True}
        owner, items = self._owner(rec, None), []
        for kind, new_id in zip(kinds, self._new_ids(len(kinds))):
            row = {"id": new_id, "source": "memory", "project_id": p["project_id"], "kind": kind,
                   "title": playbook_for(kind)["title"], "details": "", "requested_by": p["lead_id"], "owner": owner,
                   "task_id": None, "created_on": as_of, "stage": "open", "status": "open", "closed": False}
            cr["requests"].append(row)
            items.append(self._item(row, "kickoff", p))
        note = _note(p["csm_id"], "kickoff_ready", [], {
            "project_id": p["project_id"], "project_name": p["name"], "request_count": len(items),
            "titles": [i["title"] for i in items]})
        return {"client_message": self._client_plan(cr, rec, items), "notes": [note]}

    # -- plan helpers
    def _item(self, r, stage, profile):
        pb = playbook_for(r["kind"])
        return {"request_id": r["id"], "project_id": r["project_id"], "kind": r["kind"], "title": r["title"],
                "stage": stage, "created_on": r["created_on"], "first_asked_on": r.get("first_asked"),
                "owner": r.get("owner"), "project_name": profile["name"] if profile else r["project_id"],
                "ask": pb["ask"], "steps": pb["steps"], "least_privilege": pb["least_privilege"]}

    def _client_plan(self, cr, rec, items):
        to = self._owner(rec, [i["owner"] for i in items]) if items else None
        if not to:
            return None
        for i in items:
            i.pop("owner")
        cr["client_items"] = items
        return {"to": to, "to_name": self._name(to), "items": items}

    def _owner(self, rec, owners):
        contacts = (rec.get("contacts") or {})
        ids = [c["person_id"] for c in contacts.get("contacts", [])]
        counts = {o: (owners or []).count(o) for o in set(owners or []) if o in ids}
        return max(sorted(counts), key=lambda o: counts[o]) if counts else contacts.get("suggested_owner")

    def _name(self, person_id):
        person = self.parts.directory.get(person_id) if person_id else None
        return person["name"] if person else str(person_id)

    def _csm(self, projects, r, area):
        p = projects.get(r["project_id"])
        return p["csm_id"] if p else self.parts.directory.csm_of(area)

    def _developer(self, ctx, profile):
        who = ctx.task.inputs.get("requested_by") or ctx.task.caller_id
        if self.parts.directory.is_devx(who):
            return who
        return profile["lead_id"] if profile else self.parts.directory.csm_of(ctx.task.area_id)

    def _new_ids(self, n):
        count = self.parts.memory.conn.execute("SELECT COUNT(*) FROM items WHERE item_id LIKE 'CRQ-N%'").fetchone()[0]
        return [f"CRQ-N{count + k + 1:04d}" for k in range(n)]

    # decide
    def decision_prompt(self, understood):
        return ("Write the messages for this plan. For the client message write one friendly message that lists every "
                "item with its steps and access level. For each note write one short plain message from its facts. "
                'Reply with final JSON only: {"client_message": {"to", "text", "request_ids"} or null, '
                '"notes": [{"to", "topic", "text"}]}.\n' + MARK + json.dumps(understood, indent=1))

    def parse_decision(self, final_text):
        data = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", final_text.strip()))
        if not isinstance(data.get("notes", []), list):
            raise ValueError("notes must be a list")
        data.setdefault("notes", [])
        data.setdefault("client_message", None)
        return data

    # check: nothing leaves unless it matches the plan and is safe
    def check(self, ctx, decision, understood):
        problems, plan_cm, cm = [], understood.get("client_message"), decision.get("client_message")
        if plan_cm and not isinstance(cm, dict):
            problems.append("the client message is missing")
        elif cm and not plan_cm:
            problems.append("a client message was not planned")
        elif cm:
            problems += self._check_client_message(ctx, cm, plan_cm)
        plan_notes = {(n["to"], n["topic"]): n for n in understood["notes"]}
        seen = set()
        for i, n in enumerate(decision["notes"]):
            key, tag = (n.get("to"), n.get("topic")), f"note {i + 1}"
            seen.add(key)
            if key not in plan_notes:
                problems.append(f"{tag}: no planned note for {key[0]!r} about {key[1]!r}")
                continue
            if not self.parts.directory.is_devx(n["to"]):
                problems.append(f"{tag}: recipient {n['to']!r} is not a DevX person")
            text = n.get("text")
            if not isinstance(text, str) or not text.strip():
                problems.append(f"{tag}: text is empty")
                continue
            if has_secret(text):
                problems.append(f"{tag}: text holds a secret")
            problems += [f"{tag}: id {rid} is not in the text" for rid in plan_notes[key]["request_ids"] if rid not in text]
        problems += [f"missing note for {k[0]!r} about {k[1]!r}" for k in sorted(set(plan_notes) - seen)]
        return problems

    def _check_client_message(self, ctx, cm, plan_cm):
        problems, text, person = [], cm.get("text"), self.parts.directory.get(cm.get("to"))
        if cm.get("to") != plan_cm["to"]:
            problems.append(f"client message goes to {cm.get('to')!r}, the plan says {plan_cm['to']!r}")
        if not person or person["is_devx"] or person["client_id"] != ctx.task.area_id:
            problems.append(f"{cm.get('to')!r} is not a contact of this client")
        if not isinstance(text, str) or not text.strip():
            return problems + ["client message text is empty"]
        if has_secret(text):
            problems.append("client message holds a secret")
        if asks_for_password(text):
            problems.append("client message asks the client for a password")
        if sorted(cm.get("request_ids", [])) != sorted(i["request_id"] for i in plan_cm["items"]):
            problems.append("client message request_ids do not match the plan")
        problems += [f"client message leaves out {i['title']!r}" for i in plan_cm["items"] if i["title"] not in text]
        for item in plan_cm["items"]:
            dup = _existing_equivalent(item, ctx.notes["cr"]["universe"]) if item["stage"] in ("new_ask", "kickoff") else None
            if dup:
                problems.append(f"duplicate ask: {item['title']!r} is already {dup['status']} as {dup['id']}")
        return problems

    # act: one client message (held for approval) and the private notes
    def act(self, ctx, decision):
        calls, cm = [], decision.get("client_message")
        if cm:
            calls.append(ToolCall("client-msg", "send_client_message", {
                "client_contact_id": cm["to"], "text": cm["text"], "request_ids": cm["request_ids"]}))
        for n, note in enumerate(decision["notes"]):
            calls.append(ToolCall(f"note-{n}", "send_private_message",
                                  {"to_person_id": note["to"], "text": note["text"], "kind": note["topic"]}))
        return calls

    # remember: requests as items and problems as cases; secrets are masked first
    def remember(self, ctx, decision, acted):
        cr, memory, area = ctx.notes["cr"], self.parts.memory, ctx.task.area_id
        stamp = f"{ctx.task.inputs['as_of']}T09:00"
        verdict = next((a["verdict"] for a in acted if a["call"].name == "send_client_message"), None)
        stages = {i["request_id"]: i["stage"] for i in cr["client_items"]} if verdict in ("ask", "allow") else {}
        for r in cr["requests"]:
            item_id = r["id"] if r["id"].startswith("CRQ-N") else f"CRQ-{r['id']}"
            status = r["stage"]
            if r["id"] in stages and status in ("open", "asked", "reminded"):
                status = "reminded" if stages[r["id"]].startswith("reminder") else "asked"
            fields = {k: r.get(k) for k in ("kind", "title", "details", "project_id", "task_id", "requested_by", "owner")}
            if memory.get_item(item_id) is None:
                memory.add_item(area, "client_request", mask(json.dumps({**fields, "request_id": r["id"]})),
                                topic=r["project_id"], status=status, source=SOURCE, source_ref=ctx.run_id,
                                owner_id=r["requested_by"], item_id=item_id, created_at=f"{r['created_on']}T00:00")
            elif memory.get_item(item_id)["status"] != status:
                memory.set_item_status(item_id, status)
        for rid, stage in stages.items():
            memory.add_item(area, "client_ask", "new_ask" if stage in ("new_ask", "kickoff") else stage, topic=rid,
                            status="proposed" if verdict == "ask" else "sent", source=SOURCE, source_ref=ctx.run_id,
                            created_at=stamp)
        for rid in cr["told"]:
            memory.add_item(area, "client_notice", "access_ready", topic=rid, status="sent", source=SOURCE,
                            source_ref=ctx.run_id, created_at=stamp)
        cases = [memory.add_case(ctx.run_id, NAME, area, c["subject"], SEVERITY[c["signal"]], mask_all(c["evidence"]),
                                 created_at=stamp) for c in cr["cases"]]
        return {"cases": cases, "requests_tracked": len(cr["requests"]), "held": list(ctx.held),
                "blocked_days": cr["blocked_days"]}


def make_pack(parts) -> ClientRequestsPack:
    return ClientRequestsPack(parts)


def _read(ctx, name, args):
    out = ctx.notes["invoke_tool"](name, args)
    if out["verdict"] != "allow":
        raise RuntimeError(f"read {name} not allowed: {out['result']}")
    text = out["result"]
    start, end = text.find("{"), text.rfind("}")  # outside-text tools arrive wrapped
    data = json.loads(text[start:end + 1])
    if "error" in data:
        raise RuntimeError(f"read {name} failed: {data['error']}")
    return data


def _note(to, topic, request_ids, facts):
    return {"to": to, "topic": topic, "request_ids": request_ids, "facts": facts}


def _case(subject, signal, row, evidence):
    return {"subject": subject, "signal": signal,
            "evidence": {"request_id": row["id"], "project_id": row["project_id"], "kind": row["kind"],
                         "title": row["title"], **evidence}}


def _from_table(r, asks):
    row = {"id": r["request_id"], "source": "table", "project_id": r["project_id"], "kind": r["kind"],
           "title": r["title"], "details": "", "requested_by": r["requested_by"], "owner": r["owner_contact_id"],
           "task_id": r["task_id"], "created_on": r["created_on"], "status": r["status"], "closed": r["closed"],
           "days_open": r["days_open"], "reminders": r["reminders_sent"], "reminders_told": r["reminders_sent"],
           "first_asked": r["first_asked_on"],
           "last_contact": r["last_contact_on"], "replied": r["replied_since_last_contact"],
           "escalated": r["escalated"], "blocked_tasks": r["blocked_tasks"], "secret": r["secret_in_chat"],
           "granted_on": r["granted_on"], "stage": r["status"]}
    return _with_asks(row, asks.get(row["id"], []))


def _from_item(item, asks):
    data = json.loads(item["text"])
    row = {"id": data.get("request_id") or item["item_id"], "source": "memory", "project_id": data["project_id"],
           "kind": data["kind"], "title": data["title"], "details": data.get("details") or "",
           "requested_by": data["requested_by"], "owner": data.get("owner"), "task_id": data.get("task_id"),
           "created_on": item["created_at"][:10], "status": "open", "closed": False, "days_open": None,
           "reminders": 0, "reminders_told": 0, "first_asked": None, "last_contact": None, "replied": False, "escalated": False,
           "blocked_tasks": [], "secret": False, "granted_on": None, "stage": item["status"]}
    return _with_asks(row, asks.get(row["id"], []))


def _with_asks(row, asks):
    """Fold in the asks and reminders this agent proposed or sent. They are not in the requests table."""
    for a in asks:
        day = a["created_on"]
        row["first_asked"] = min(filter(None, [row["first_asked"], day]))
        row["last_contact"] = max(filter(None, [row["last_contact"], day]))
        row["reminders"] += a["text"].startswith("reminder")
        row["reminders_told"] += a["text"].startswith("reminder") and a["status"] == "sent"
    if row["source"] == "memory":
        row["status"] = "reminded" if row["reminders"] else "asked" if row["first_asked"] else "open"
    return row


def _from_check(c):
    return {"id": c["request_id"], "source": "table", "project_id": c["project_id"], "kind": c["kind"],
            "title": c["title"], "details": "", "requested_by": c["requested_by"], "owner": None, "task_id": None,
            "created_on": c["checked_at"][:10], "status": "verified", "closed": True, "stage": "verified"}


def _due_stage(r, as_of):
    """new_ask, reminder_1 (2 days after the first ask), reminder_2 (4 days), or None."""
    if r["status"] not in OPEN_STATES:
        return None
    if r["first_asked"] is None:
        return "new_ask"
    if r["replied"]:
        return None
    since_ask, since_last = days_between(as_of, r["first_asked"]), days_between(as_of, r["last_contact"])
    if r["reminders"] == 0 and since_ask >= 2:
        return "reminder_1"
    if r["reminders"] == 1 and since_ask >= 4 and since_last >= 2:
        return "reminder_2"
    return None


def _text_of(r):
    return f"{r['title']} {r.get('details') or ''}"


def _words(text):
    return {w for w in re.findall(r"[a-z0-9.-]+", text.lower()) if w not in STOP}


def _same_target(a, b):
    """Same store, domain or subject. Two stores of one client are not the same."""
    ta, tb = set(HOST_RE.findall(a.lower())), set(HOST_RE.findall(b.lower()))
    if ta and tb:
        return bool(ta & tb)
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return False
    return wa <= wb or wb <= wa or len(wa & wb) / len(wa | wb) >= 0.6


def _duplicate_pairs(rows):
    """(later, earlier): same project, kind and target, different developers, created within 5 days."""
    pairs, ordered = [], sorted(rows, key=lambda r: (r["created_on"], r["id"]))
    for i, later in enumerate(ordered):
        for earlier in ordered[:i]:
            if (earlier["project_id"], earlier["kind"]) == (later["project_id"], later["kind"]) \
                    and earlier["requested_by"] != later["requested_by"] \
                    and days_between(later["created_on"], earlier["created_on"]) <= DUPLICATE_WINDOW_DAYS \
                    and _same_target(_text_of(earlier), _text_of(later)):
                pairs.append((later, earlier))
                break
    return pairs


def _existing_equivalent(item, universe):
    """An earlier request for the same thing that is open or granted, or None."""
    for u in universe:
        if u["id"] != item["request_id"] and (u["project_id"], u["kind"]) == (item["project_id"], item["kind"]) \
                and u["status"] != "cancelled" and u.get("stage") != "merged" \
                and (u["created_on"], u["id"]) < (item["created_on"], item["request_id"]) \
                and _same_target(_text_of(u), item["title"]):
            return u
    return None
