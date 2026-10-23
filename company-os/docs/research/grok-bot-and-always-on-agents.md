# Grok Bot, Muse, Dots and open-source always-on harnesses

Researched Oct 18, 2026 by a Sonnet researcher agent, for the Company OS prototype (`company-os/`). The x.ai and openai.com pages returned 403, so most Grok Bot and Dots claims are from search snippets and blogs (unverified).

## Answers
- **Grok Bot (xAI).** "Grokbots" in Rachit's notes is the same product (unverified). Beta from Aug 11, 2026: an always-on agent on a cloud computer that signs into your apps. Routines run on a schedule or on events (new Slack message, Git commit). A "teach" mode turns a demonstrated task into a reusable skill with approval boundaries. Approval can be required before send, publish, delete, buy or production changes. Prices: launch bundles ($120 per seat with Cursor Teams, $200 with Cursor Ultra, $300 SuperGrok Heavy) are out of date; one snippet says $30, $100 and $200 a month now. All unverified. Sources: interestingengineering.com, developersdigest.tech, venturebeat.com, mindstudio.ai.
- **Muse (Meta)**, confirmed from https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/ : a personal agent in its own cloud VM and browser; keeps working after the app closes; memory; asks before sensitive actions; audit trail. A separate agent, Sentinel, isolated from Muse, must approve anything that reaches the internet.
- **Dots** is OpenAI's (announced Sep 29, 2026), not a startup. Each dot has its own cloud computer; works between requests; Custom Rules, Activity View, auto review; first dot with the Pro plan. Unverified (9to5google.com, reworked.co).
- **OpenClaw**, confirmed: https://github.com/openclaw/openclaw (MIT). Local gateway; scheduler (cron, intervals, condition watchers), authenticated webhooks `/hooks/*`, Gmail Pub/Sub; unknown senders must pair first; tools run on the host unless sandboxed.
- **Hermes Agent**, confirmed: https://github.com/NousResearch/hermes-agent (MIT). Memory as markdown (`MEMORY.md`, `USER.md`) plus FTS5 session search; command approval, DM pairing, container sandboxes; cron docs at hermes-agent.nousresearch.com.

## Ideas worth copying (and what we did)
1. A permission checker the worker agent cannot steer (Muse's Sentinel). Ours is plain code in `guardrails/`, so the model cannot argue with it.
2. A pre-check that skips the model call on quiet ticks (Hermes cron). Added to the lifecycle kit: no signals, no model call.
3. Scheduled runs may not create new schedules (Hermes cron). No agent gets a tool that creates triggers.
4. A global pause switch and one catch-up run after downtime (Hermes cron). Pause added to the way-in check.
5. One trigger layer for schedules, webhooks and events, each run in a fresh session (OpenClaw). Matches our `triggers/`.
6. Turn a demonstrated task into a reviewable skill with its own approval limits (Grok Bot, unverified). Not built; a later idea.
