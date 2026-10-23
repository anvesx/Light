"""Records a few real-Claude samples (Sonnet through the `claude` CLI) for the console's real-sample view.

Uses the person's Claude plan, so it only runs with --yes. About one model call per sample.
Usage: python3 -m evaluation.record_real_samples --yes [sample ...]
"""
import json
import os
import sys
import tempfile
import time

from agents.meeting_prep.live_copilot.live_session import LiveSession
from control_plane.company_brain import inbox
from control_plane.company_brain.pipeline import read_manifest_file
from control_plane.connectors.spend_tools import make_trip_alternatives
from contract.types import RunContext, Task
from evaluation.real_pipeline_brain import BRAIN_AGENTS, manifest_rows
from wiring.build_company_os import build_company_os

OUT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web_console", "real_model_samples.json")
MODEL = "claude-cli"
SEEDED = (*BRAIN_AGENTS, "meeting_prep", "deal_brief", "live_copilot", "spend_advisor")


def _model_calls(cos, run_id):
    steps = [s["step"] for s in cos.memory.run_steps(run_id)]
    return steps.count("model_call") + steps.count("retry")


def _sample(cos, what, who, run_id, status, reason, final_text, started, **extra):
    letters = [{"to": m["to_person_id"], "kind": m["kind"], "text": m["text"]} for m in cos.outbox.messages() if m["run_id"] == run_id]
    return {"what": what, "asked_by": who, "run_id": run_id, "status": status, "reason": reason or "", "final_text": final_text or "",
            "letters": letters, "calls": _model_calls(cos, run_id), "seconds": round(time.time() - started, 1), **extra}


def project_brief(cos):
    started = time.time()
    r = cos.run("meeting_prep", "P05", "C04", inputs={"event_id": "EV115"}, model=MODEL)
    return _sample(cos, "Project brief for the PR05 client sync (Akbar, CSM)", "P05", r.run_id, r.status, r.reason, r.final_text, started)


def deal_brief(cos):
    started = time.time()
    r = cos.run("deal_brief", "P03", "C07", inputs={"deal_id": "L20"}, model=MODEL)
    return _sample(cos, "Deal brief for CareNest (Anthony, Growth)", "P03", r.run_id, r.status, r.reason, r.final_text, started)


def live_call_summary(cos):
    started = time.time()
    session = LiveSession.start(cos, "P05", "LC02", model=MODEL)
    for n in sorted(session.script):
        session.hear(n)
    out = session.end()
    return _sample(cos, "End summary of live call LC02 (Akbar, CSM)", "P05", out["run_id"], out["status"], "", out["summary"], started,
                   next_steps=out["next_steps"], suggestions=len(out["suggestions"]))


def finance_trip_card(cos):
    started = time.time()
    ctx = RunContext("SAMPLE", Task("spend_advisor", "P01", "devx-internal", "request", inputs={}), None)
    cards = json.loads(make_trip_alternatives(cos.data_conn).fn({"from": "2000-01-01"}, ctx))["trips"]
    card = next(c for c in cards if c["cheaper_flights"] or c["cheaper_hotels"])
    r = cos.run("spend_advisor", "P01", "devx-internal", inputs={"question": f"Was trip {card['trip_id']} too expensive? What was cheaper?",
                                                                 "as_of": cos.clock.today}, model=MODEL)
    return _sample(cos, f"Finance trip card for {card['trip_id']} (Ammar, Admin)", "P01", r.run_id, r.status, r.reason, r.final_text, started)


def cleaner_on_hinglish_source(_cos=None):
    """Runs on its own unseeded brain, so the chosen MedBridge source is still new."""
    started = time.time()
    cos = build_company_os(agents=("brain_cleaner",), state_dir=tempfile.mkdtemp(prefix="real_cleaner_"), real_model=MODEL)
    row = next(r for r in manifest_rows() if r["origin_ref"] == "SRC25")  # MedBridge client sync, Hinglish
    got = inbox.receive(cos.brain, cos.data_conn, kind=row["kind"], content=read_manifest_file(row), origin_ref=row["origin_ref"],
                        hint_area=row["hint_area"], received_at=row["arrives_at"], force=True)
    r = cos.run("brain_cleaner", "system", got["area_id"], trigger_kind="event", inputs={"source_id": got["source_id"]}, model=MODEL)
    raw = {l["line_no"]: l["text"] for l in cos.brain.source_lines(got["source_id"])}
    pairs = [{"line_no": l["line_no"], "raw": raw[l["line_no"]], "clean": l.get("clean_text")} for l in cos.brain.source_lines(got["source_id"])]
    return _sample(cos, "Cleaner on a Hinglish MedBridge source (SRC25)", "system", r.run_id, r.status, r.reason, r.final_text, started,
                   lines=pairs)


SAMPLES = {"project_brief": project_brief, "deal_brief": deal_brief, "cleaner_hinglish": cleaner_on_hinglish_source,
           "live_call_summary": live_call_summary, "finance_trip_card": finance_trip_card}


def main(argv):
    if "--yes" not in argv:
        print("This calls real Claude (Sonnet) on your plan. Run again with --yes to record.")
        return 1
    wanted = [a for a in argv if not a.startswith("--")] or list(SAMPLES)
    cos = build_company_os(SEEDED, state_dir=tempfile.mkdtemp(prefix="real_samples_"), real_model=MODEL, seed_brain=True)
    try:
        with open(OUT_PATH) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data["samples"] = {k: v for k, v in data.get("samples", {}).items() if k in SAMPLES}  # drop the v1 agents' samples
    for name in wanted:
        print(f"recording {name} ...", flush=True)
        try:
            data["samples"][name] = SAMPLES[name](cos)
        except Exception as e:  # keep going: one sample failing should not lose the others
            data["samples"][name] = {"status": "error", "reason": f"{type(e).__name__}: {e}"}
        s = data["samples"][name]
        print(f"  {s.get('status')} {str(s.get('reason', ''))[:120]} | calls {s.get('calls')} | {s.get('seconds')}s", flush=True)
    data["model"] = "claude-cli (sonnet)"
    data["generated_at"] = time.strftime("%Y-%m-%d")
    with open(OUT_PATH, "w") as f:
        json.dump(data, f, indent=1)
    print("saved", OUT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
