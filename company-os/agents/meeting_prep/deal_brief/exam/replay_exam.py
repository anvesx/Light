"""Replay exam for the deal brief: both live deals get similar clients, every kickoff topic and objection answered, no outside cites."""
import json
import os

from company_data import DB_PATH
from wiring.build_company_os import build_company_os

from .exam_fixture import seed_exam_library

KEY_PATH = os.path.join(os.path.dirname(DB_PATH), "answer_keys.json")
EXAM, AGENT = "deal_brief_replay", "deal_brief"


def _cited_areas(cos, cites):
    areas = set()
    for cite in cites:
        if cite.startswith("PB-"):
            areas |= {p["area_id"] for p in cos.brain.playbooks() if p["playbook_id"] == cite}
        else:
            item = cos.brain.get_brain_item(cite)
            areas.add(item["area_id"] if item else "missing")
    return areas


def _score_deal(cos, d):
    result = cos.run(AGENT, "P03", d["area_id"], inputs={"deal_id": d["deal_id"]})
    out = {"deal_id": d["deal_id"], "status": result.status}
    if result.status != "done" or not result.final_text:
        return {**out, "similar_ok": False, "kickoff_missing": d["kickoff_topics"], "objection_missing": d["objection_topics"],
                "forbidden_cites": 0}
    brief = json.loads(result.final_text)
    by_id = {p["playbook_id"]: p["area_id"] for p in cos.brain.playbooks()}
    top2 = {by_id[s["playbook_id"]] for s in brief["similar"][:2]}
    asked = {q["topic"] for q in brief["kickoff_questions"]}
    covered = {i.get("topic") for i in brief["closing_ideas"]}
    cites = [c for r in brief["closing_ideas"] + brief["risks"] + brief["kickoff_questions"] for c in r["cites"]]
    areas = _cited_areas(cos, cites)
    return {**out, "similar_ok": top2 == set(d["similar_top2"]),
            "kickoff_missing": sorted(set(d["kickoff_topics"]) - asked),
            "objection_missing": sorted(set(d["objection_topics"]) - covered),
            "forbidden_cites": len(areas & set(d["must_not_cite_areas"]))}


def run_exam(cos=None) -> dict:
    with open(KEY_PATH) as f:
        key = json.load(f)["brain"]
    cos = cos or build_company_os(agents=(AGENT,))
    used_fixture = not cos.brain.playbooks()
    if used_fixture:  # the Playbook writer has not filled the library yet
        seed_exam_library(cos.brain, cos.data_conn, key)
    rows = [_score_deal(cos, d) for d in key["deals"]]
    result = {"deals": len(rows), "used_fixture": used_fixture, "per_deal": rows,
              "similar_ok": sum(r["similar_ok"] for r in rows),
              "kickoff_missing": sum(len(r["kickoff_missing"]) for r in rows),
              "objection_missing": sum(len(r["objection_missing"]) for r in rows),
              "forbidden_cites": sum(r["forbidden_cites"] for r in rows),
              "failed_runs": [r["deal_id"] for r in rows if r["status"] != "done"]}
    for metric in ("similar_ok", "kickoff_missing", "objection_missing", "forbidden_cites"):
        cos.memory.add_score(EXAM, AGENT, metric, float(result[metric]), detail={"deals": len(rows)})
    return result


def judge(r):
    """Return (what is measured, result text, passed) for this exam's raw result."""
    ok = (not r["failed_runs"] and r["similar_ok"] == r["deals"] and r["kickoff_missing"] == 0
          and r["objection_missing"] == 0 and r["forbidden_cites"] == 0)
    text = (f"similar top 2 right {r['similar_ok']}/{r['deals']}; kickoff topics missed {r['kickoff_missing']}; "
            f"objections without an idea {r['objection_missing']}; forbidden cites {r['forbidden_cites']}"
            + ("; fixture library" if r["used_fixture"] else ""))
    return "similar deals, kickoff topics, objections, no forbidden cites", text, ok


if __name__ == "__main__":
    print(json.dumps(run_exam(), indent=2))
