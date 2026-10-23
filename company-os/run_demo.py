"""One simulated working day on the dummy company: triggers fire, agents run, people get messages."""
import shutil
import tempfile
from types import SimpleNamespace

from agents.finance.travel_booking import service
from control_plane.company_brain import pipeline
from evaluation.run_all_exams import close_all
from control_plane.triggers.dispatch import dispatch
from control_plane.triggers.inbox_trigger import InboxTrigger
from control_plane.triggers.timer_trigger import TimerTrigger
from wiring.agent_registry import available_agents as registry_available
from wiring.build_company_os import build_company_os


def available_agents():
    """Packs that can be built now, and (name, reason) pairs for the rest."""
    ok, missing = registry_available()
    return ok, list(missing.items())


def _first_line(text, width=70):
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    return line if len(line) <= width else line[:width - 3] + "..."


def _schedule(cos, agents):
    """Daily rows: finance watch for DevX."""
    rows = []
    if "finance_watch" in agents:
        rows.append({"agent": "finance_watch", "area_id": "devx-internal", "every": "daily"})
    return rows


def _outcome(cos, result):
    """Return (status, one-line outcome) for one run."""
    if result.status == "refused":
        return "refused", result.reason or "the way-in check said no"
    if result.status == "done" and result.final_text == "quiet":
        return "quiet", "nothing to report, no model call"
    if result.status == "failed":
        return "failed", result.reason or _first_line(result.final_text)
    sent = [m for m in cos.outbox.messages() if m["run_id"] == result.run_id]
    waiting = [a for a in cos.approvals.pending() if a["run_id"] == result.run_id]
    parts = [f"{len(sent)} message(s) sent"]
    if waiting:
        parts.append(f"{len(waiting)} approval(s) waiting")
    return result.status, ", ".join(parts)


def run_day(agents=None, state_dir=None):
    """Run the v2 day. Returns a dict with the runs, messages, approvals, refusal and cost numbers."""
    names = tuple(agents) if agents else available_agents()[0]
    cos = build_company_os(names, state_dir=state_dir, seed_brain=True)
    runs, triggers = [], []

    def note(trigger, agent, area, caller, result, line=None):
        status, outcome = _outcome(cos, result)
        line = line or outcome
        runs.append({"trigger": trigger, "agent": agent, "area": area, "caller": caller, "status": status,
                     "outcome": line, "run_id": result.run_id})
        return result

    def ask(agent, caller, area, inputs, trigger="request"):
        return note(trigger, agent, area, caller, cos.run(agent, caller, area, trigger_kind=trigger, inputs=inputs))

    if "brain_cleaner" in names:  # the day's recordings and emails arrive and go through the four brain agents
        arrived = InboxTrigger().due(SimpleNamespace(now=f"{cos.clock.today}T23:59"))
        triggers.append(f"inbox: {len(arrived)} new source(s) arrived today")
        for row in arrived:
            got = pipeline.ingest_file(cos, kind=row["kind"], content=pipeline.read_manifest_file(row), filename=row["file"],
                                       hint_area=row.get("hint_area"), origin_ref=row["origin_ref"], received_at=row["arrives_at"])
            for step in got.get("steps", []):
                if step["run_id"]:
                    note("inbox", step["agent"], got["area_id"], "system",
                         SimpleNamespace(status=step["status"], reason="", final_text="", run_id=step["run_id"]), line=step["summary"])

    if "finance_watch" in names:
        timer_tasks = TimerTrigger(_schedule(cos, names)).due(cos.clock)
        triggers.append(f"timer: {len(timer_tasks)} daily run(s) due")
        dispatch(timer_tasks, lambda t: note("timer", t.agent, t.area_id, t.caller_id, cos.runner.run(cos.packs[t.agent], t)))

    if "meeting_prep" in names:
        triggers.append("request: Akbar asks for the project brief for the PR05 event")
        ask("meeting_prep", "P05", "C04", {"event_id": "EV115"})
    if "deal_brief" in names:
        triggers.append("request: Anthony asks for the deal brief for CareNest")
        ask("deal_brief", "P03", "C07", {"deal_id": "L20"})
    if "travel_booking" in names:
        triggers.append("request: Akbar asks for a trip; the booking waits for an Admin")
        trip = service.request_trip(cos, "P05", "flights for 2 people Mumbai to Pune on 2026-10-28, back on 2026-10-29")
        note("request", "travel_booking", "devx-internal", "P05",
             SimpleNamespace(status=trip["status"], reason=trip.get("reason", ""), final_text="", run_id=trip["run_id"]))

    refusal = None
    if "finance_watch" in names:
        triggers.append("request: Anthony (Growth) asks for a finance run")
        res = ask("finance_watch", "P03", "devx-internal", {})
        refusal = {"caller": "P03", "status": runs[-1]["status"], "reason": res.reason}

    messages = cos.outbox.messages()
    entries = cos.ledger.entries
    cache = [e["cache"] for e in entries]
    cost = {"calls": len(entries), "cache_hits": cache.count("hit"), "cache_writes": cache.count("write"),
            "usd": round(sum(e["cost_usd"] for e in entries), 4)}
    return {"date": cos.clock.today, "agents": names, "triggers": triggers, "runs": runs, "messages": messages,
            "approvals": cos.approvals.pending(), "refusal": refusal, "cost": cost, "cos": cos}


def print_day(day):
    cos = day["cos"]
    name = lambda pid: f"{pid} {p['name']}" if (p := cos.directory.get(pid)) else pid
    print(f"One day at the dummy company: {day['date']}")
    print("\nTriggers")
    for t in day["triggers"]:
        print(f"  {t}")
    print("\nRuns (trigger, agent, area, status, outcome)")
    for r in day["runs"]:
        print(f"  {r['trigger']:<8} {r['agent']:<15} {r['area']:<13} {r['status']:<8} {r['outcome']}")
    print("\nMessages people received (who, kind, first line)")
    for m in day["messages"]:
        print(f"  {name(m['to_person_id'])} | {m['kind']} | {_first_line(m['text'])}")
    print(f"\nApprovals waiting: {len(day['approvals'])}")
    for a in day["approvals"]:
        print(f"  {a['approval_id']} {a['agent']} {a['tool']}: {_first_line(a['reason'])}")
    if day["refusal"]:
        r = day["refusal"]
        print(f"\nRefusal example: Growth person {r['caller']} asked for a finance run -> {r['status']} ({r['reason']})")
    c = day["cost"]
    print(f"\nCost and cache: {c['calls']} model calls, {c['cache_hits']} cache hits, "
          f"{c['cache_writes']} cache writes, ${c['usd']:.4f} total")


def main():
    state = tempfile.mkdtemp(prefix="company_os_demo_")
    try:
        _, skipped = available_agents()
        day = run_day(state_dir=state)
        print_day(day)
        if skipped:
            print("\nNot built yet, skipped: " + ", ".join(name for name, _ in skipped))
        close_all(day["cos"])
    finally:
        shutil.rmtree(state, ignore_errors=True)


if __name__ == "__main__":
    main()
