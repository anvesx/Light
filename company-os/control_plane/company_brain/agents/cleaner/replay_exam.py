"""Replay exam for the Cleaner: every manifest source is cleaned; no line is dropped, none is left without text or a review row."""
import json

from control_plane.company_brain import inbox
from control_plane.company_brain.extract_rules import needs_translation
from control_plane.company_brain.pipeline import read_manifest_file
from control_plane.company_brain.write_tools import untranslated_lines
from control_plane.triggers.inbox_trigger import MANIFEST_PATH

EXAM, AGENT = "brain_cleaner_replay", "brain_cleaner"


def run_exam(cos) -> dict:
    rows = json.loads(MANIFEST_PATH.read_text())["sources"]
    stats = {"sources": 0, "non_english": 0, "translated": 0, "review_entries": 0, "missing": 0, "dropped": 0,
             "raw_changed": 0, "failed_runs": []}
    for row in rows:
        got = inbox.receive(cos.brain, cos.data_conn, kind=row["kind"], content=read_manifest_file(row),
                            origin_ref=row["origin_ref"], hint_area=row["hint_area"], received_at=row["arrives_at"], force=True)
        sid = got["source_id"]
        if cos.brain.get_source(sid)["area_id"] == "hold":
            continue
        before = [l["text"] for l in cos.brain.source_lines(sid)]
        result = cos.run(AGENT, "system", got["area_id"], trigger_kind="event", inputs={"source_id": sid})
        if result.status != "done":
            stats["failed_runs"].append(row["origin_ref"])
            continue
        source, lines = cos.brain.get_source(sid), cos.brain.source_lines(sid)
        gaps = set(untranslated_lines(cos.brain, source))
        stats["sources"] += 1
        stats["dropped"] += len(before) - len(lines)
        stats["raw_changed"] += sum(1 for a, b in zip(before, lines) if a != b["text"])
        for line in lines:
            if line["clean_text"] is None:
                stats["missing"] += 1
            if needs_translation(line["text"]) or line["line_no"] in gaps:
                stats["non_english"] += 1
                if line["line_no"] in gaps:
                    stats["review_entries"] += 1
                elif line["clean_text"] and line["clean_text"] != line["text"]:
                    stats["translated"] += 1
                else:
                    stats["missing"] += 1
    return stats


def judge(r):
    """Return (what is measured, result text, passed) for this exam's raw result."""
    ok = (not r["failed_runs"] and r["dropped"] == 0 and r["raw_changed"] == 0 and r["missing"] == 0 and r["sources"] > 0)
    text = (f"{r['translated']} translated, {r['review_entries']} in review, of {r['non_english']} non-English lines; "
            f"{r['dropped']} dropped, {r['raw_changed']} raw changed")
    return "non-English lines have clean text or a review entry", text, ok


if __name__ == "__main__":
    from evaluation.run_all_exams import close_all
    from wiring.build_company_os import build_company_os
    c = build_company_os(agents=(AGENT,))
    print(judge(run_exam(c)))
    close_all(c)
