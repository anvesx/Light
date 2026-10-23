# company_memory

**Role in the harness:** Company memory: the one shared store every agent reads and writes, split into one area per client. It also keeps the append-only run log.

The shared company memory. It follows the meeting graph in `docs/graph/`: items, links between them,
plus agent runs, run steps, cases and exam scores. One SQLite file: `company_memory.db`.

## What is inside
- `schema.sql`: tables `areas`, `items`, `links`, `runs`, `run_steps`, `cases`, `scores`.
- `memory_store.py`: `MemoryStore(path=DB_PATH, clock=None)`.
- `scoped_memory.py`: `ScopedMemory`, a read-only view of the allowed areas.
- `area_denied.py`: `AreaDenied`, raised on a read outside the allowed areas.

## Rules
- Every item is in exactly one area: one per client, `devx-internal`, `hold` (client not decided yet), or `playbooks` (the library area of redacted playbooks).
- Run steps are append only. No method updates or deletes them, and the database refuses it too.
- Link types: `supersedes`, `answers`, `refines`, `follows_up`, `about`, `contradicts`, `same_as`.
- An item added with an `item_id` that exists is a no-op, so loaders can run twice.

## Use
```python
from company_memory import MemoryStore, AreaDenied
mem = MemoryStore("/tmp/x.db")
i = mem.add_item("C01", "question", "Which gateway?", topic="payment-gateway", created_at="2026-05-01")
view = mem.scoped(["C01"])
view.items("C01", kinds="question", before="2026-06-01")
view.items("C02")  # raises AreaDenied
```

## Files in this folder

| File | What it does |
|---|---|
| `area_denied.py` | The error raised when memory is read outside the areas a run may see. |
| `memory_store.py` | SQLite company memory: items by area, links, runs, append-only run steps, cases, scores. |
| `schema.sql` | Company memory tables. Safe to run many times. |
| `scoped_memory.py` | A read-only view of company memory limited to the areas one run may see. |
