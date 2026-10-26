"""Lessons: a failed check leaves a candidate lesson in the runtime store. A person promotes it into experience.md.

Candidates never go into the source tree. The log is an append-only JSONL file in a data folder.
"""
import json
import os
import sys
import uuid
from pathlib import Path

CANDIDATES_FILE = "lesson_candidates.jsonl"
SIGNAL_FAILED_CHECK = "failed check"
DIR_ENV = "COMPANY_OS_LESSONS_DIR"


class LessonLog:
    def __init__(self, directory):
        self.path = Path(directory) / CANDIDATES_FILE

    def _append(self, row):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:   # one write per row, so rows do not interleave
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    def record_failed_check(self, agent, run_id, problems, when=""):
        """Write one candidate for each problem of a failed check. Returns the candidates."""
        rows = [{"id": f"{run_id}-{n}", "kind": "candidate", "agent": agent, "run_id": run_id, "problem": str(problem),
                 "signal": SIGNAL_FAILED_CHECK, "at": str(when)} for n, problem in enumerate(problems, 1)]
        for row in rows:
            self._append(row)
        return rows

    def candidates(self, agent=None, status="candidate"):
        """Candidates with their current status (candidate or promoted), oldest first."""
        if not self.path.is_file():
            return []
        rows, promoted = [], set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line) if line.strip() else {}
            if row.get("kind") == "candidate":
                rows.append(row)
            elif row.get("kind") == "promoted":
                promoted.add(row["id"])
        rows = [{**r, "status": "promoted" if r["id"] in promoted else "candidate"} for r in rows]
        return [r for r in rows if (agent is None or r["agent"] == agent) and (status is None or r["status"] == status)]

    def mark_promoted(self, candidate_id):
        self._append({"kind": "promoted", "id": candidate_id})


def promote_candidate(log, candidate_id, lesson, folder):
    """Add `lesson` (written by a person) to the agent folder's experience.md and mark the candidate promoted."""
    lesson = " ".join(str(lesson).split())
    if not lesson:
        raise ValueError("the lesson text is empty")
    if not any(c["id"] == candidate_id for c in log.candidates(status="candidate")):
        raise ValueError(f"no open candidate {candidate_id}")
    path = Path(folder) / "experience.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if f"- {lesson}" not in text.split("\n"):
        path.write_text(text.rstrip("\n") + f"\n- {lesson}\n" if text else f"- {lesson}\n", encoding="utf-8")
    log.mark_promoted(candidate_id)
    return lesson


def main(argv=None):
    """`list [--agent NAME]` and `promote ID "lesson text"`. The data folder comes from COMPANY_OS_LESSONS_DIR."""
    args = list(sys.argv[1:] if argv is None else argv)
    directory = os.environ.get(DIR_ENV)
    if not directory or not args or args[0] not in ("list", "promote"):
        print(f"usage: {DIR_ENV}=<dir> python3 -m lifecycle_kit.lessons list [AGENT] | promote ID \"lesson text\"")
        return 2
    log = LessonLog(directory)
    if args[0] == "list":
        for c in log.candidates(args[1] if len(args) > 1 else None):
            print(f"{c['id']}\t{c['agent']}\t{c['signal']}\t{c['problem']}")
        return 0
    from importlib import import_module
    from wiring.agent_registry import AGENTS
    chosen = next((c for c in log.candidates() if c["id"] == args[1]), None)
    if chosen is None or len(args) < 3:
        print("give an open candidate id and the lesson text")
        return 2
    folder = Path(import_module(f"{AGENTS[chosen['agent']]}.pack").__file__).parent
    print("promoted:", promote_candidate(log, args[1], args[2], folder))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
