"""Exam for the live copilot: play LC01 and LC02 against the brain and compare with the answer key."""
import json

from wiring.build_company_os import build_company_os

from .call_brain_seed import KEYS, seed_history
from .live_session import LiveSession

EXAM, AGENT = "live_copilot_replay", "live_copilot"


def _p95(values):
    values = sorted(values)
    return values[min(len(values) - 1, int(0.95 * len(values)))] if values else 0.0


def _score_call(cos, spec):
    session = LiveSession.start(cos, spec["viewer"], spec["call_id"])
    for n in sorted(session.script):
        session.hear(n)
    result = session.end()
    got = result["suggestions"]
    window, found, used = spec["window_lines"], [], set()
    for exp in spec["expected"]:
        hit = next((i for i, s in enumerate(got) if i not in used and s["topic"] == exp["topic"]
                    and 0 <= s["line_no"] - exp["line_no"] <= window), None)
        if hit is not None:
            used.add(hit)
            found.append({**exp, "got_line": got[hit]["line_no"], "got_kind": got[hit]["kind"],
                          "cites": got[hit]["cites"]})
    want = {e["topic"] for e in spec["expected"]}
    false = [s for i, s in enumerate(got) if i not in used and s["topic"] not in want]
    contradictions = [e for e in spec["expected"] if e["kind"] == "contradiction"]
    contradiction_ok = all(any(f["got_kind"] == "contradiction" and f["topic"] == c["topic"] for f in found) for c in contradictions)
    return {"call_id": spec["call_id"], "expected": len(spec["expected"]), "found": len(found),
            "recall": len(found) / len(spec["expected"]), "false_suggestions": len(false), "contradiction_ok": contradiction_ok,
            "has_contradiction": bool(contradictions), "timings_ms": session.timings_ms, "summary_ok": bool(result["summary"]),
            "run_status": result["status"]}


def run_exam(cos=None) -> dict:
    cos = cos or build_company_os(agents=(AGENT,))
    if cos.brain.brain_items("C04", kinds=["decision"]) == []:
        seed_history(cos)
    with open(KEYS, encoding="utf-8") as f:
        specs = json.load(f)["brain"]["live_calls"]
    rows = [_score_call(cos, s) for s in specs]
    times = [t for r in rows for t in r["timings_ms"]]
    result = {"calls": len(rows), "mean_recall": sum(r["recall"] for r in rows) / len(rows),
              "max_false": max(r["false_suggestions"] for r in rows),
              "contradiction_found": all(r["contradiction_ok"] for r in rows if r["has_contradiction"]),
              "p95_ms": _p95(times), "per_call": [{k: v for k, v in r.items() if k != "timings_ms"} for r in rows]}
    for metric in ("mean_recall", "max_false", "p95_ms"):
        cos.memory.add_score(EXAM, AGENT, metric, result[metric], detail={"calls": len(rows)})
    cos.memory.add_score(EXAM, AGENT, "contradiction_found", 1.0 if result["contradiction_found"] else 0.0)
    return result


def judge(r):
    """Return (what is measured, result text, passed) for this exam's raw result."""
    ok = r["mean_recall"] >= 0.9 and r["max_false"] <= 1 and r["contradiction_found"] and r["p95_ms"] < 200
    text = (f"recall {r['mean_recall']:.0%}, at most {r['max_false']} false per call, contradiction "
            f"{'found' if r['contradiction_found'] else 'MISSED'}, p95 {r['p95_ms']:.1f} ms per line")
    return "expected questions suggested in time, speed per line", text, ok


if __name__ == "__main__":
    print(json.dumps(run_exam(), indent=2))
