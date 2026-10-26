# Memory map

Which store areas this agent reads and writes, and why. Role scopes decide which areas a run may read.

## Reads

- The new items of one source and the older items near them (`brain_read_source_items`).

## Writes

- Links between items (`brain_add_links`).
- The scope of an item (`brain_set_scope`) and its state, such as superseded or resolved (`brain_set_state`).

## Why

- Links show what changed and what repeats. Code decides most links and the model only confirms the unsure pairs.
- Every tool refuses items outside the run's area.
