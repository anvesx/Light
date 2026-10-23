# control_plane

**Role in the harness:** The control plane: everything that makes the core useful for a company. It holds the checks, the memory, the brain, the people surface, the triggers and the connectors.

The control plane sits on top of `core/`. It decides who may run what, stores what happened, and brings data in and out. The core never imports it. `wiring/build_company_os.py` joins the two.

Folders:
- `guardrails/`: roles, the way-in check and the check before every action.
- `company_memory/`: the run log, areas and memory items.
- `company_brain/`: facts from meetings and records, each with evidence.
- `people_surface/`: the outbox and approvals that reach people.
- `triggers/`: what starts a task (calendar, inbox and similar).
- `connectors/`: tools that read or write company data.
