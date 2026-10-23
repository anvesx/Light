"""Replay exam for the Playbook writer: link the keyed brain, write the four playbooks, compare topics, check evidence and leaks."""
import json

from control_plane.company_brain.agents.linker.replay_exam import KEY_PATH, seed_keyed_brain
from control_plane.company_brain.redaction import find_leaks
from core.fake_model import FakeModel
from wiring.build_company_os import build_company_os

from .fake_brain import leaky_brain

EXAM, AGENT = "brain_playbook_replay", "brain_playbook"
SECTION_OF = {"later_changed_topics": "later_changed_to", "went_right_topics": "went_right", "went_wrong_topics": "went_wrong"}


def _topics(playbook, section):
    return {e["topic"] for e in playbook["sections"][section]}


def run_exam(cos=None):
    from control_plane.company_brain.agents.linker.replay_exam import AGENT as LINKER
    cos = build_company_os(agents=(LINKER, AGENT), extra_backends={"sonnet-5-5": FakeModel({AGENT: leaky_brain, LINKER: leaky_brain})})
    try:
        seeded = seed_keyed_brain(cos)
        for ref in seeded["order"]:
            area = cos.brain.get_source(seeded["sources"][ref])["area_id"]
            cos.run(LINKER, "system", area, trigger_kind="event", inputs={"source_id": seeded["sources"][ref]})
        with open(KEY_PATH) as f:
            keys = json.load(f)["brain"]["playbooks"]
        rows, leaks = [], 0
        for k in keys:
            r = cos.run(AGENT, "system", k["area_id"], trigger_kind="event", inputs={"deal_id": k["deal_id"]})
            pb = next((p for p in cos.brain.playbooks() if p["deal_id"] == k["deal_id"]), None)
            row = {"deal_id": k["deal_id"], "status": r.status, "published": pb is not None, "missing_topics": [],
                   "foreign_entries": 0}
            if pb:
                for key_name, section in SECTION_OF.items():
                    row["missing_topics"] += [f"{section}:{t}" for t in sorted(set(k[key_name]) - _topics(pb, section))]
                for entries in pb["sections"].values():
                    for e in entries:
                        row["foreign_entries"] += (not e["item_ids"]) or any(
                            (cos.brain.get_brain_item(i) or {}).get("area_id") != k["area_id"] for i in e["item_ids"])
                leaks += len(find_leaks(json.dumps(pb["sections"]) + pb["client_label"], cos.data_conn))
            rows.append(row)
        leaks += sum(len(find_leaks(c["question"] + " " + c["why"], cos.data_conn)) for c in cos.brain.checklist())
        before = len(cos.brain.playbooks())
        bad = cos.run(AGENT, "system", keys[0]["area_id"], trigger_kind="event", model="sonnet-5-5", inputs={"deal_id": keys[0]["deal_id"]})
        return {"playbooks": len(cos.brain.playbooks()), "expected": len(keys), "rows": rows, "leaks": leaks,
                "checklist_items": len(cos.brain.checklist()),
                "leak_blocked": bad.status == "failed" and "leaks" in bad.reason and len(cos.brain.playbooks()) == before}
    finally:
        for part in (cos.data_conn, cos.memory, cos.outbox, cos.approvals):
            part.close()


def judge(r):
    """Return (what is measured, result text, passed) for this exam's raw result."""
    missing = sum(len(x["missing_topics"]) for x in r["rows"])
    foreign = sum(x["foreign_entries"] for x in r["rows"])
    ok = (r["playbooks"] == r["expected"] and not missing and not foreign and r["leaks"] == 0 and r["leak_blocked"]
          and all(x["status"] == "done" for x in r["rows"]))
    text = (f"{r['playbooks']}/{r['expected']} playbooks, {missing} required topics missing, {foreign} foreign entries, "
            f"{r['leaks']} leaks, leaky draft {'refused' if r['leak_blocked'] else 'NOT refused'}")
    return "playbooks: required topics, own-area evidence, leaks", text, ok


if __name__ == "__main__":
    print(json.dumps(run_exam(), indent=1, default=str))
