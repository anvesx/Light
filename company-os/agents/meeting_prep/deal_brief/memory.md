# Memory map

Which store areas this agent reads and writes, and why. Role scopes decide which areas a run may read.

## Reads

- The items of the deal's own area (`deal_overview`).
- The redacted playbooks of the library area `playbooks` (`similar_playbooks`, `kickoff_checklist`). This agent sets `reads_library`.

## Writes

- One private message to the person who asked (`send_private_message`). No memory item is written.

## Why

- Past deals teach what to ask and what to expect. Only redacted playbooks are safe to read across clients.
- The deal's own items give the facts. Other clients' areas stay closed.
