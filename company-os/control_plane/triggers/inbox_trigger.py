"""Inbox trigger: gives each manifest source that has arrived on the simulated clock, once."""
import json
from pathlib import Path

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "company_data" / "brain_sources" / "manifest.json"


class InboxTrigger:
    def __init__(self, manifest_path=MANIFEST_PATH, include_history=False):
        """History sources are already in the brain at build, so they are left out unless include_history is set."""
        rows = json.loads(Path(manifest_path).read_text(encoding="utf-8"))["sources"]
        self.rows = [r for r in rows if include_history or not r.get("history")]
        self._given = set()

    def due(self, clock):
        """Rows whose arrives_at is not after the clock, never the same row twice."""
        ready = [r for r in self.rows if r["origin_ref"] not in self._given and r["arrives_at"] <= clock.now]
        self._given.update(r["origin_ref"] for r in ready)
        return ready
