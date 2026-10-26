"""Replay exam for the Linker: load the sources, store the answer-key items, link each source, compare with the key links."""
import json
import os

from control_plane.company_brain.inbox import receive
from control_plane.company_brain.record_sync import sync_records
from company_data import DB_PATH
from wiring.build_company_os import build_company_os

BRAIN_DIR = os.path.join(os.path.dirname(DB_PATH), "brain_sources")
KEY_PATH = os.path.join(os.path.dirname(DB_PATH), "answer_keys.json")
EXAM, AGENT = "brain_linker_replay", "brain_linker"
STATE_CHANGING = ("supersedes", "contradicts")


def _load_json(*path):
    with open(os.path.join(*path), encoding="utf-8") as f:
        return json.load(f)


def seed_keyed_brain(cos, until_ref=None):
    """Store every manifest source with clean lines and the answer-key items. Returns {"sources": {ref: id}, "items": {key: id}}."""
    brain = cos.brain
    sync_records(cos.data_conn, brain)
    manifest = _load_json(BRAIN_DIR, "manifest.json")["sources"]
    translations = _load_json(BRAIN_DIR, "translations.json")
    key = {s["origin_ref"]: s for s in _load_json(KEY_PATH)["brain"]["sources"]}
    out = {"sources": {}, "items": {}, "order": []}
    for row in manifest:
        with open(os.path.join(BRAIN_DIR, row["file"]), "rb") as f:
            content = f.read()
        content = content if row["kind"] == "docx" or row["kind"] == "email" else content.decode("utf-8")
        got = receive(brain, cos.data_conn, kind=row["kind"], content=content, origin_ref=row["origin_ref"],
                      hint_area=row["hint_area"], received_at=row["arrives_at"])
        sid = got["source_id"]
        raw = brain.source_lines(sid)
        brain.set_clean_lines(sid, [{"line_no": l["line_no"], "speaker": l["speaker"],
                                     "clean_text": translations.get(f"{row['origin_ref']}:{l['line_no']}", l["text"])} for l in raw])
        clean = {l["line_no"]: l for l in brain.source_lines(sid)}
        for it in key.get(row["origin_ref"], {}).get("items", []):
            span = range(it["line_from"], it["line_to"] + 1)
            text = " ".join(clean[n]["clean_text"] for n in span)
            out["items"][it["key"]] = brain.add_brain_item(
                got["area_id"], it["kind"], text, topic=it["topic"], source_id=sid, line_from=it["line_from"], line_to=it["line_to"],
                quote_raw=" ".join(clean[n]["text"] for n in span), quote_clean=text, confidence=0.9)
        out["sources"][row["origin_ref"]] = sid
        out["order"].append(row["origin_ref"])
    return out


def run_exam(cos=None):
    cos = cos or build_company_os(agents=(AGENT,))
    seeded = seed_keyed_brain(cos)
    key = _load_json(KEY_PATH)["brain"]
    runs = []
    for ref in seeded["order"]:
        sid = seeded["sources"][ref]
        area = cos.brain.get_source(sid)["area_id"]
        if area == "hold":
            continue
        r = cos.run(AGENT, "system", area, trigger_kind="event", inputs={"source_id": sid})
        runs.append({"source": ref, "status": r.status})
    by_id = {v: k for k, v in seeded["items"].items()}
    made = {(by_id[l["from_id"]], l["rel"], by_id[l["to_id"]]) for i in by_id for l in cos.memory.links_of(i)
            if l["from_id"] in by_id and l["to_id"] in by_id}
    expected = {(l["from"], l["rel"], l["to"]) for s in key["sources"] for l in s["links"]}
    expected_pairs = {(f, t): rel for f, rel, t in expected} | {(t, f): rel for f, rel, t in expected}
    wrong = [m for m in made if m not in expected and (
        (m[0], m[2]) in expected_pairs or m[1] in STATE_CHANGING)]
    merged = 0
    for a, b in key["duplicates"]:
        ia, ib = (cos.brain.get_brain_item(seeded["items"][k]) for k in (a, b))
        linked = {(a, "same_as", b), (b, "same_as", a)} & made
        states = sorted((ia["state"], ib["state"]))
        merged += bool(linked) and states == ["active", "resolved"]
    return {"expected_links": len(expected), "found_links": len(expected & made), "missing": sorted(expected - made),
            "wrong_links": len(wrong), "wrong": sorted(wrong), "extra_links": sorted(made - expected - set(wrong)),
            "duplicates": len(key["duplicates"]), "duplicates_merged": merged, "failed_runs": [r for r in runs if r["status"] != "done"]}


def judge(r):
    """Return (what is measured, result text, passed) for this exam's raw result."""
    ok = r["found_links"] == r["expected_links"] and r["wrong_links"] == 0 and r["duplicates_merged"] == r["duplicates"] \
        and not r["failed_runs"]
    text = (f"{r['found_links']}/{r['expected_links']} key links, {r['wrong_links']} wrong, "
            f"{r['duplicates_merged']}/{r['duplicates']} duplicates merged")
    return "key links found, wrong links, duplicates merged", text, ok


if __name__ == "__main__":
    print(json.dumps(run_exam(), indent=1, default=str))
