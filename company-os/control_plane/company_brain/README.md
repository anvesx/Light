# company_brain

**Role in the harness:** The company brain store. Any file enters through the inbox, is stored as a source with numbered lines, and every fact keeps evidence that points back to those lines.

Tables share the company memory file (`brain_*` tables; items live in the memory `items` table). The four brain agents come in wave 2 (`agents/`).

## Files
- `schema.sql`: tables for sources, lines, item facts, evidence, projects, deals, revenue, review queue, playbooks, checklist.
- `brain_store.py`: `BrainStore(memory_store, data_conn=None)`, all writes and reads.
- `scoped_brain.py`: `ScopedBrain`, read-only. Other areas raise `AreaDenied`. The library needs the `playbooks` area.
- `inbox.py`: `receive(...)` reads a file, routes it, stores it. Same `origin_ref` twice returns the stored source. `should_ingest(meeting, data_conn)` skips internal Fathom meetings (no outside attendee, no client in the title, no `#brain`).
- `source_readers.py`: Fathom JSON, docx, eml, chat export, plain text to `(meta, lines)`.
- `area_router.py`: hint, contact email or name, client email domain, calendar event title, project name in the title, client name in the title, then `hold`.
- `language.py`, `topic_lexicon.py`: language guess and whole-word topic cues.
- `retrieval.py`: `similar_deals`, 0.5 for the same industry group plus 0.5 times tag overlap.
- `sample_content.py`: `seed_sample(brain, data_conn)`, a small fixed brain for tests.

## Rules
- No item without evidence (a source, a line range and a raw quote).
- Raw source text and raw lines never change. Clean text is stored beside them.
- Nothing waits for a person. An item under 0.6 confidence, or from an untranslated line, is stored at once with state `unconfirmed` and `confirmed: false`.
- A newer statement that contradicts an older one wins: the older item becomes `superseded` and both keep a `contradicts` link (`resolve_contradiction`).
- The review queue is an optional check list. Confirm sets an item `active`. Reject sets it `dropped`. Nothing is deleted.
- Only a source that cannot be routed goes to `hold`. An Admin sorts those.
