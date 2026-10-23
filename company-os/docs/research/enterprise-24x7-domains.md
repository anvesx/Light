# Enterprise 24/7 agents: practice domains and real examples

Researched Oct 15, 2026 by a Sonnet researcher agent. **All claims come from web search summaries only. The agent did not open the pages.** Treat every point as secondary unless marked otherwise.

## Ranked domains for a first practice harness (the agent's judgment, unverified)
1. **GitHub repo / PR watcher.** Public data, read-only, easy success check (review comments vs merged fixes). Uses webhooks + schedule, memory of past PRs, approval before commenting, evals.
2. **Cloud cost / spend watcher.** Use synthetic or public billing data. Clear anomaly checks. Needs a real daily loop. Real data is sensitive.
3. **Support ticket triage.** Public datasets exist, labels give a clear check. Weaker 24/7 loop.
4. **SRE alert investigator.** High teaching value. Safe data is hard to get. Root-cause accuracy is hard to judge.
5. **Sales research agent.** Public web data. Vague success check. Not researched.

## Real-world examples
- **AWS FinOps Agent** (public preview, June 2026). Runs on a schedule, on anomaly events, or on questions. Opens Jira tickets or Slack messages to the resource owner. Confirmed from docs: https://aws.amazon.com/blogs/aws-cloud-financial-management/aws-finops-agent-is-now-public-preview/ . No savings numbers given.
- **Ramp Policy Agent.** Cites policy text, escalates 10 to 15% of items. Vendor claims 99% accuracy and 7x more out-of-policy spend caught. Ramp gives two different baselines for the 7x. https://ramp.com/blog/ramp-policy-agent-ga-launch
- **Cleric at BlaBlaCar** (SRE). 553 investigations, 78% actionable, under 2 minutes each. Vendor-sourced via https://nudgebee.com/resources/blog/best-ai-sre-tools-for-reducing-mttr

## Evidence and patterns (secondary)
- Independent checks are rare. Google reports 10 to 44% cut in time to mitigate: https://www.ajayk.sh/blog/aiops-2026-incident-response-agents-mttr/
- Intercom Fin claims 76% resolution. A 500-ticket test found 38%: https://builts.ai/blog/intercom-fin-ai-review/
- Ping budget: 3 to 5 per user per day: https://tianpan.co/blog/2026-05-13-background-agents-notification-budget-attention-economy . 4-hour dedupe window: https://arxiv.org/pdf/2607.07721
- Evaluation: golden set of 50 to 300 cases, 2 to 5% human review. One shadow test fell from 100% on golden tests to 70% on live traffic: http://agenticarchitect.ai/blog/shadow-testing

## Not verified
Independent savings numbers for spend agents; Brex and sales examples; how agents "teach back"; evaluation of multi-day agents; any primary source.
