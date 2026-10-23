# Client requests agent

**Role in the harness:** The client requests agent: it collects what developers need from the client (store access, DNS records, cloud roles, keys, files, decisions), asks once, reminds politely, checks that access really works, and keeps secrets out of every message and record.

CSMs are DevX's project managers. Today developers ask through the CSM or directly. That causes slow back-and-forth, double asks, no reminders, and nobody counting the days a task waited.

**What it does for each person**
- **Developers:** write one line ("need theme access on store X"). The agent finds the client owner and checks if it was already asked or granted. If so, it merges the ask and tells you. If not, it logs it for the next daily message. It tells you when access is granted and checked.
- **CSMs:** get a kickoff checklist when a SOW is signed, so most asks happen once at the start. Every message to a client waits for your approval. You are told when a request is stuck (9 days), when "granted" access fails its check, and when a client pastes a secret in chat.
- **Clients:** get at most one message per day, with step-by-step instructions, asking for the smallest access that works (a collaborator invite, a limited cloud role, sign-in through your own account). Reminders come after 2 and 4 days, politely.

**The daily round** (timer, every client): batches the open asks into one message, sends reminders, merges duplicates, and escalates to the CSM after 9 days. The code finds every case. The model only writes the words.

**Safety rules**
- Never ask for a password. Ask for delegated access. A check stops any message that asks for one.
- A secret in client text (`pw:`, a password, an API key, a long token) is masked inside the tools, before the agent sees it. It is never copied into memory, messages, approvals or logs. The CSM is told to have it changed and moved to the vault.
- A request is done only when an access check passed. A granted request whose check failed is opened again and the CSM and developer are told.
- `send_client_message` is a risky tool. It always waits for a CSM or the CEO. Only after approval does it post, as kind `client_message`, and only to a contact of the same client.
- The agent reads one client at a time and cannot message anyone outside the client's own contacts and DevX.

**Tools:** `project_profile`, `open_client_requests`, `access_check_results`, `client_contacts_for` (read); `send_private_message`; `send_client_message` (risky, held for approval).

**Three ways to start it**
- Timer: the daily round.
- Request: inputs `kind`, `project_id`, optional `task_id`, `details`.
- SOW signed: input `sow_id`, for the kickoff checklist.
Optional input `as_of` (YYYY-MM-DD) sets the date.

**How it is scored:** `replay_exam.py` replays each client day by day from 2026-08-01 to today and compares with the planted cases: CR-1 a request asked twice, CR-2 a request stuck for 9 days, CR-3 granted but the check failed, CR-4 a password pasted in chat. It scores found or missed, days late, whether the right people were told, false alarms on two look-alikes (one reminder then granted; two different stores of one client), and secret leaks (must be 0). Scores are saved in company memory.

## Files in this folder

| File | What it does |
|---|---|
| `__init__.py` | Marks the folder as a Python package. |
| `fake_brain.py` | Stand-in for the model, for tests and demos: writes the messages from the plan. |
| `pack.py` | The agent: kickoff, developer request and daily round, the check step, and the risky `send_client_message` tool. |
| `replay_exam.py` | Replay exam: runs the daily round day by day and scores it against the planted cases. |
| `request_playbooks.py` | One short playbook per kind of request: what to ask, the steps for the client, the least-privilege rule. |
| `secret_redaction.py` | Finds and masks passwords, keys and tokens, and spots a message that asks for a password. |
