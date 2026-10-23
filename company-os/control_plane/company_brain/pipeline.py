"""Pipeline: one source goes through Cleaner, Extractor, Linker and Playbook writer as normal guarded runs."""
import json
from pathlib import Path

from control_plane.triggers.inbox_trigger import MANIFEST_PATH

from . import inbox

STEPS = ("brain_cleaner", "brain_extractor", "brain_linker", "brain_playbook")
CLOSED_DEAL_STAGES = ("won", "lost")


def _step(agent, status, summary, run_id=None):
    return {"agent": agent, "run_id": run_id, "status": status, "summary": summary}


def _summary(cos, run_id, result):
    if result.status != "done":
        return result.reason or result.status
    for s in reversed(cos.memory.run_steps(run_id)):
        if s["step"] == "remember" and s["detail"].get("summary"):
            return s["detail"]["summary"]
        if s["step"] == "quiet":
            return "nothing to do"
    return "done"


def _closed_deals(cos, source):
    deals = cos.brain.deals([source["area_id"]])
    if source.get("deal_id"):
        deals = [d for d in deals if d["deal_id"] == source["deal_id"]]
    return [d for d in deals if d["stage"] in CLOSED_DEAL_STAGES]


def _run_playbooks(cos, source, caller_id):
    """One Playbook writer run per closed deal (it needs a deal id). Returns the step row."""
    deals = _closed_deals(cos, source)
    if not deals:
        return _step("brain_playbook", "skipped", "the deal or project is not closed")
    results = [cos.run("brain_playbook", caller_id, source["area_id"], trigger_kind="event",
                       inputs={"source_id": source["source_id"], "deal_id": d["deal_id"]}) for d in deals]
    bad = next((r for r in results if r.status != "done"), None)
    last = results[-1]
    return _step("brain_playbook", (bad or last).status, _summary(cos, (bad or last).run_id, bad or last), last.run_id)


def process_source(cos, source_id, *, caller_id="system") -> dict:
    """Run the agents in order. A source never blocks: an agent that is missing is skipped, a failed Cleaner stops the chain."""
    source = cos.brain.get_source(source_id)
    if source is None:
        raise KeyError(source_id)
    out = {"source_id": source_id, "area_id": source["area_id"], "steps": []}
    if source["area_id"] == "hold":  # an Admin sorts it first; reassign, then process again
        out["held"] = True
        return out
    for agent in STEPS:
        if agent not in cos.packs:
            out["steps"].append(_step(agent, "skipped", "this agent is not available"))
            continue
        if agent == "brain_playbook":
            out["steps"].append(_run_playbooks(cos, source, caller_id))
            continue
        result = cos.run(agent, caller_id, source["area_id"], trigger_kind="event", inputs={"source_id": source_id})
        out["steps"].append(_step(agent, result.status, _summary(cos, result.run_id, result), result.run_id))
        if agent == "brain_cleaner" and result.status != "done":
            cos.brain.set_source_status(source_id, "failed")
            break
        if agent == "brain_extractor" and cos.brain.get_source(source_id)["status"] == "cleaned":
            cos.brain.set_source_status(source_id, "extracted")  # a source with no facts is still finished
    return out


def ingest_file(cos, *, kind, content, filename=None, hint_area=None, origin_ref=None, received_at=None,
                submitted_by=None, force=True) -> dict:
    """Receive one file, then process it. A duplicate or a skipped file is not processed again."""
    received = inbox.receive(cos.brain, cos.data_conn, kind=kind, content=content, filename=filename,
                             received_at=received_at, hint_area=hint_area, origin_ref=origin_ref,
                             submitted_by=submitted_by, force=force)
    if received.get("source_id") is None or received.get("duplicate"):
        return {**received, "steps": []}
    return {**received, **process_source(cos, received["source_id"])}


def read_manifest_file(row, manifest_path=MANIFEST_PATH):
    path = Path(manifest_path).parent / row["file"]
    return path.read_bytes() if row["kind"] in ("docx", "email") else path.read_text(encoding="utf-8")


def ingest_manifest(cos, *, history=True, manifest_path=MANIFEST_PATH, rows=None) -> list:
    """Ingest the manifest sources whose `history` flag matches (or the given rows). Returns one result per source."""
    rows = rows if rows is not None else [r for r in json.loads(Path(manifest_path).read_text())["sources"]
                                          if bool(r["history"]) == history]
    return [ingest_file(cos, kind=r["kind"], content=read_manifest_file(r, manifest_path), filename=r["file"],
                        hint_area=r.get("hint_area"), origin_ref=r["origin_ref"], received_at=r["arrives_at"])
            for r in rows]
