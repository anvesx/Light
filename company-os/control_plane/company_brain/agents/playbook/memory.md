# Memory map

Which store areas this agent reads and writes, and why. Role scopes decide which areas a run may read.

## Reads

- The items, projects and deal data of one client's area (`brain_read_deal`).

## Writes

- A redacted playbook in the library area `playbooks` (`brain_publish_playbook`).
- Kickoff checklist questions (`brain_save_checklist`).

## Why

- Other clients may read only the redacted playbook, never the deal itself.
- Nothing is saved when the check finds a leak.
