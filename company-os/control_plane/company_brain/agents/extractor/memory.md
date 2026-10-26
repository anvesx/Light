# Memory map

Which store areas this agent reads and writes, and why. Role scopes decide which areas a run may read.

## Reads

- The clean lines of one source of the run's area (`brain_read_source`).

## Writes

- Items with their source lines (`brain_add_items`). Confidence of 0.6 or more is stored active, lower is stored unconfirmed.

## Why

- Items are the facts the other agents read. Each one must point back to its lines as evidence.
- The tool refuses a source outside the run's area.
