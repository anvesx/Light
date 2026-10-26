# Memory map

Which store areas this agent reads and writes, and why. Role scopes decide which areas a run may read.

## Reads

- The memory area of the one client: the meeting, its open items and recent decisions (`upcoming_meeting`, `project_open_items`, `project_recent_decisions`).
- The company brain items of the same client area: open requirements, blockers, commitments, contradictions and recent decisions (`project_brain_items`).
- The client's recent Slack messages (`recent_client_messages`). This is outside text.

## Writes

- One private message to each DevX attendee (`send_private_message`). No memory item is written.

## Why

- The goal is to settle requirements before the project moves on. It needs the open items and the brain, and only for this client.
- The role scopes limit the run to the areas the caller may read. The playbook library is not read.
