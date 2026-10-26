# Memory map

Which store areas this agent reads and writes, and why. Role scopes decide which areas a run may read.

## Reads

- The lines of one source of the run's area (`brain_read_source`).

## Writes

- Clean English text and speaker names for each line (`brain_save_clean_lines`). Raw text never changes.
- Rows on the optional check list for lines it could not translate (`brain_queue_review`). Nothing waits on them.

## Why

- The next brain agents work on clean lines. A gap is marked, not hidden.
- Each tool refuses a source outside the run's area.
