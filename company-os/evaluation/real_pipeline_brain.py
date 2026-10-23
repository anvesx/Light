"""Builds a brain through the real pipeline (inbox, Cleaner, Extractor, Linker, Playbook writer), not from answer keys."""
import json

from control_plane.company_brain import pipeline
from control_plane.company_brain.record_sync import sync_records
from control_plane.triggers.inbox_trigger import MANIFEST_PATH
from wiring.build_company_os import build_company_os

BRAIN_AGENTS = ("brain_cleaner", "brain_extractor", "brain_linker", "brain_playbook")


def manifest_rows():
    """Every F1 source row, in arrival order."""
    return sorted(json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["sources"], key=lambda r: r["arrives_at"])


def build_real_pipeline_cos(agent):
    """A Company OS for one agent whose brain holds every F1 source, in arrival order, run through the four brain agents."""
    cos = build_company_os(agents=(*BRAIN_AGENTS, agent))
    sync_records(cos.data_conn, cos.brain)
    pipeline.ingest_manifest(cos, rows=manifest_rows())
    return cos


def key_item_ids(cos, key_all):
    """Map each answer-key item (like SRC25-9) to the real item ids that cite the same source lines. Returns {key: [ids]}."""
    brain, found = cos.brain, {}
    for src in key_all["brain"]["sources"]:
        source = brain.source_by_ref(src["origin_ref"])
        items = brain.brain_items(src["area_id"], state=None, source_id=source["source_id"]) if source else []
        for it in src["items"]:
            hits = [i for i in items if any(e["source_id"] == source["source_id"] and e["line_from"] <= it["line_to"]
                                            and e["line_to"] >= it["line_from"] for e in i["evidence"])]
            same_topic = [i for i in hits if i["topic"] == it["topic"]]
            found[it["key"]] = [i["item_id"] for i in (same_topic or hits)]
    return found
