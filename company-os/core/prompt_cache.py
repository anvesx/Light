"""Simulated prompt cache: tells whether the system + tools prefix would be a cache hit."""
import hashlib
import json
from datetime import datetime

TTL_MINUTES = 5


def prefix_parts(system: str, tools: list) -> dict:
    """The cacheable prefix as named parts. Tools are sorted by name."""
    specs = [{"name": t.name, "description": t.description, "params": t.params}
             for t in sorted(tools, key=lambda t: t.name)]
    return {"system": system, "tools": json.dumps(specs, sort_keys=True)}


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _to_time(now) -> datetime:
    return now if isinstance(now, datetime) else datetime.fromisoformat(now)


class PromptCache:
    def __init__(self):
        self._seen = {}   # agent -> {"hash", "parts", "at"}
        self.log = []     # one row per check: agent, result, changed

    def check(self, agent: str, prefix_text: str, now, parts: dict | None = None) -> str:
        """Return "hit" or "write". A hit needs the same prefix from the same agent within 5 minutes."""
        now = _to_time(now)
        parts = parts or {"prefix": prefix_text}
        digest = _digest(prefix_text)
        part_hashes = {k: _digest(v) for k, v in parts.items()}
        prev = self._seen.get(agent)
        changed = []
        if prev is None:
            changed = ["new"]
        elif prev["hash"] != digest:
            changed = [k for k in part_hashes if prev["parts"].get(k) != part_hashes[k]] or ["prefix"]
        elif (now - prev["at"]).total_seconds() > TTL_MINUTES * 60:
            changed = ["expired"]
        result = "write" if changed else "hit"
        self._seen[agent] = {"hash": digest, "parts": part_hashes, "at": now}
        self.log.append({"agent": agent, "result": result, "changed": changed})
        return result
