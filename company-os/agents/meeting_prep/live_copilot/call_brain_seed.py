"""Fills a brain with the history sources from the F1 answer keys, so a live call has something to check against."""
import json
import os

from control_plane.company_brain.inbox import receive
from company_data import DB_PATH

SOURCES = os.path.join(os.path.dirname(DB_PATH), "brain_sources")
KEYS = os.path.join(os.path.dirname(DB_PATH), "answer_keys.json")
BINARY = ("docx", "email")


def _content(entry):
    mode = "rb" if entry["kind"] in BINARY else "r"
    with open(os.path.join(SOURCES, entry["file"]), mode, **({} if mode == "rb" else {"encoding": "utf-8"})) as f:
        return f.read()


def seed_history(cos):
    """Store every history source, its key items (with evidence) and the kickoff checklist. Returns {key: item_id}."""
    brain = cos.brain
    with open(os.path.join(SOURCES, "manifest.json"), encoding="utf-8") as f:
        manifest = {m["origin_ref"]: m for m in json.load(f)["sources"]}
    with open(os.path.join(SOURCES, "translations.json"), encoding="utf-8") as f:
        trans = json.load(f)
    with open(KEYS, encoding="utf-8") as f:
        keys = json.load(f)["brain"]
    ids = {}
    for src in keys["sources"]:
        ref, entry = src["origin_ref"], manifest.get(src["origin_ref"])
        if entry is None or not entry["history"]:
            continue
        got = receive(brain, cos.data_conn, kind=entry["kind"], content=_content(entry), origin_ref=ref, hint_area=src["area_id"])
        lines = brain.source_lines(got["source_id"])
        for it in src["items"]:
            raw = lines[it["line_from"] - 1]["text"]
            clean = trans.get(f"{ref}:{it['line_from']}", raw)
            ids[it["key"]] = brain.add_brain_item(src["area_id"], it["kind"], clean, topic=it["topic"], source_id=got["source_id"],
                                                  line_from=it["line_from"], line_to=it["line_to"], quote_raw=raw,
                                                  quote_clean=clean, confidence=0.9)
        for link in src["links"]:
            if link["rel"] == "supersedes" and link["to"] in ids:
                brain.set_state(ids[link["to"]], "superseded")
    industries = {r["client_id"]: r["industry"] for r in cos.data_conn.execute("SELECT client_id, industry FROM clients")}
    for deal in keys["deals"]:
        for topic in deal["kickoff_topics"]:
            brain.save_checklist_item(topic=topic, question=f"Have we settled {topic.replace('-', ' ')}?",
                                      why="Past deals added this late.", learned_from=[deal["area_id"]],
                                      industries=[industries[deal["area_id"]]])
    return ids
