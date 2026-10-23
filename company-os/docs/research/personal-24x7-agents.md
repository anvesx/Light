# 24/7 personal agents: Muse, Grok Bot, OpenClaw, Hermes

Researched Oct 15, 2026 by a Sonnet researcher agent through web pages and GitHub web listings. **Nothing was cloned, run or installed.** Labels: confirmed-from-source (a file was read on GitHub), secondary (news or blog).

## What the names are
- **Muse (Meta)**: consumer cloud agent, launched Sep 8, 2026. One VM per user. Phone calls to US businesses in beta since Sep 17. Secondary: https://techcrunch.com/2026/09/17/rival-ai-agents-instinct-and-metas-muse-both-add-the-ability-to-make-calls/ , https://www.progressiverobot.com/2026/09/27/muse-agent-dedicated-vm-tab-voice-mode-widget/
- **Muse Code**: terminal coding harness, reads AGENTS.md, has `muse skills`. Secondary: https://qainsights.com/getting-started-with-muse-code-cli-commands-syntax-and-purpose/ . The local superpowers plugin README has `muse plugins install` (confirmed locally).
- **angilyu/muse-voice-agent**: unrelated open-source voice agent. https://github.com/angilyu/muse-voice-agent
- **"Grog pot" = most likely Grok Bot** (xAI/SpaceXAI), launched Aug 11, 2026. Always-on agents, each with its own computer. Closed. $120 to $300 a month. Secondary: https://venturebeat.com/orchestration/spacexais-grok-bot-turns-agents-into-persistent-digital-coworkers-that-can-operate-your-apps-for-120-per-month
- **OpenClaw** (formerly Clawdbot, Moltbot): the open-source match. https://github.com/openclaw/openclaw
- **Hermes Agent** (Nous Research): open-source rival. https://github.com/NousResearch/hermes-agent

## Five mechanisms to copy
1. **One Gateway daemon, one serialized queue lane per session.** https://docs.openclaw.ai/concepts/agent-loop . Source dirs `src/gateway`, `src/cron` (names only).
2. **Heartbeat is a cron job.** The agent answers "nothing to report" and the gateway drops it. https://docs.openclaw.ai/gateway/heartbeat . HEARTBEAT.md is legacy; older blogs are out of date.
3. **Standing goal loop.** After each turn a judge model decides whether to continue, 20-turn cap. Hermes `gateway/run_goals.py` (confirmed-from-source).
4. **Cron tick with a file lock.** It moves `next_run_at` forward before running a job, so a job runs at most once. Hermes `cron/scheduler_tick.py`.
5. **Self-made skills with an idle-time curator** that archives and never deletes. Hermes `agent/curator.py`.

## Money
- Verified evidence is thin. Most real income comes from selling setup and hosting: https://panews.io/articles/019cd682-ae89-754f-92b1-4304328aa56f
- Best documented case: Nat Eliason's "Felix", about $3,500 (secondary).
- No evidence found for "lakhs or crores", and nothing India-specific.

## Security
- ClawHub had hundreds of malicious skills, CVE-2026-25253, thousands of exposed instances: https://blog.barrack.ai/openclaw-security-vulnerabilities-2026/
- Hermes audit findings on default config: https://github.com/NousResearch/hermes-agent/issues/7826

## Not verified
Grok Bot internals and models; `muse skills` syntax; OpenClaw loop and plugin-loader file paths; Hermes memory paths; repo listings were truncated.
