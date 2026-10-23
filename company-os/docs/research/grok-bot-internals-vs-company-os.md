# Grok Bot inside, compared with Company OS

Researched Oct 19, 2026 by a Sonnet researcher agent; written up by the lead. Primary sources: https://docs.x.ai/grok-bot (pages `/computer-and-apps`, `/approvals-security-and-privacy`, `/skills-routines-and-automations`) and https://x.ai/news/introducing-grok-bot. The fetch tool summarised these pages, so the wording below is not verbatim. About 12 claims are confirmed and 8 are unverified. The product comparison (Dots, Muse, Copilot, Glean) was not re-checked in this pass; see `grok-bot-and-always-on-agents.md`.

**Short answer: our direction is sound.** Grok Bot follows the same core pattern: always-on agents, started by schedules and events, with approval before risky actions. Grok Bot has no company brain and no per-role data rules, so those parts of Company OS have no public comparison.

## How Grok Bot works

| Point | Status |
|---|---|
| Beta launched Aug 11, 2026 | Confirmed (x.ai/news) |
| All of a user's Bots share **one** cloud computer. Bots are not a security boundary between each other. This corrects our Oct 18 note, which said each Bot has its own computer | Confirmed (`/computer-and-apps`, `/approvals-security-and-privacy`) |
| It works through the screen and browser of that computer, signed into the user's apps | Confirmed (`/computer-and-apps`) |
| Routines run on a schedule or on events, for example a Slack message or a GitHub event | Confirmed (`/skills-routines-and-automations`) |
| Teach mode: the user shows a task (up to 10 minutes of screen) and Grok Bot turns it into a skill | Confirmed |
| Approval before sensitive actions; approvals asked by a routine expire after about 10 minutes | Confirmed |
| Admin-set rules are locked; when rules conflict, "ask first" wins | Confirmed |
| "Auto Review" uses a model to judge actions | Confirmed |
| Which model it runs (Grok 4.6 is named only in secondary sources) | Unverified |
| Prices (no price on the x.ai pages) | Unverified |
| Audit logs (sources conflict) | Unverified |
| Team roles | Unverified |
| Webhooks (not documented) | Unverified |
| A shared organisation memory | Unverified; none found |

## Side by side

| Topic | Grok Bot | Company OS | Same or different |
|---|---|---|---|
| Starts work | Schedules and events | Timer, calendar, new source, a person asking | Same |
| Risky actions | Approval first, expires after about 10 minutes | Approval first, no expiry yet | Same, theirs expires |
| How it reaches data | Screen and browser on a shared cloud computer | Read-only connectors in code | Different: ours is safer and testable (strength). Risk: we have no real connectors or logins yet |
| Memory | Per Bot; Bots not isolated from each other | One company brain, every fact linked to its source line, one area per client | Different (strength) |
| Roles | Unverified | Admin, CSM and Growth, enforced on the data | Different (strength, if theirs is weak) |
| Safety checks | Model-based Auto Review plus locked admin rules | Plain-code guardrails before each run and each action | Different: ours cannot be argued with (strength) |
| Skills | Taught by demonstration | Written as agent packs | Different: theirs is easier for non-engineers |
| Meetings into memory | Not found | Fathom transcripts in Hinglish go in automatically | Ours only |

## Ideas worth copying

1. **Approvals that expire.** A held booking or letter should lapse after a set time, so an old approval is never used by mistake.
2. **A teach mode that produces a draft skill.** A person shows a task once; the system writes a draft agent pack that an engineer reviews.
3. **Limits on routines and stored run records.** Cap how many routines a person can create, and how long run records are kept.
