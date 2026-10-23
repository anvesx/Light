> Simulated opinions from one AI model role-playing 16 personas; useful for ideas and objections, not proof of demand.

## Summary

Sixteen fictional people discussed Company OS. The final verdicts were 15 "maybe" and 1 "no". Nobody said "yes".

The core design got praise. People liked plain code doing the finding, the model only writing the explanation, human approval, the audit log, the pause switch and the thin runtime.

Almost everyone distrusted the results. The scores (4 of 4, 8 of 8, 9 of 9) come from planted problems on dummy data. Many called them a unit test or a demo, not evidence.

The Project risk agent was the most disliked part. Its "hours and silence" watching was seen as surveillance of individuals. Both everyday users and enterprise leaders said this.

Pricing views were consistent. Buyers want flat or capped fees and no per-seat pricing. They also want hard cost caps, because model cost at scale is unmeasured.

## What people agree is right

- **Plain code does the finding.** Finance people said they can trace and audit rules, but not model readings of text.
- **Approval before action, plus an audit log and pause switch.** The pharma and bank leaders said these fit segregation of duties.
- **Quiet days cost nothing.** The retail COO said this matters at 300 stores.
- **A thin, readable runtime.** The agent engineer preferred 150 lines to 1,700 packages. The pharma buyer agreed that a small codebase is easier to validate.
- **One shared memory with client areas.** The industrial group CEO wants one true view without layers of softening.
- **Some agents are widely liked.** Meeting prep was the favourite of developers, the CSM and the small agency owner. Finance watch and Spend advisor were favoured by finance, pharma, the CEO and the IT buyer. Hiring forecast was favoured by both HR leaders.

## What is wrong or risky

- **The evidence is weak.** The data was planted, and the pitch admits it does not test the model's judgement. Nine examples cannot support a rate. Real ledgers have credit notes, part payments and odd entries, so false alarms are expected.
- **Project risk looks like surveillance.** "Silence" is a weak signal, because a quiet developer is often doing deep work. People fear that warnings and logs will later be used in appraisals, discipline or exit decisions. The pitch gives staff no right to see what is logged about them.
- **Prompt injection.** "Treat outside text as data" was called an intention, not a control. Client requests reads emails and chat, so it is the agent people fear most.
- **Model explanations are untested.** A confident but wrong "why" may be approved by a tired reviewer. Approval can become a rubber stamp.
- **Cost is unmeasured.** A noisy trigger could fire many runs.
- **Approval can become a bottleneck at scale.** The logistics, shared-services and industrial leaders raised this. Others (finance, bank, pharma, IT buyer) said auto-approval is risky.
- **Vendor risk.** The pitch is silent on data residency, prompt retention, validation packages, release control, reference customers and support. The IT buyer asked what happens if DevX is acquired or fails.
- **Fit.** The agents suit office records. Logistics needs field events. The 15-person agency does not have the departments the pitch assumes.
- **Adoption and staff trust.** The IT buyer has shelved a dozen tools that nobody opened after month two. The shared-services head fears staff leaving when they hear "agents watching".

## Everyday users vs big enterprise (how they differ)

**Everyday users** asked: will this help me or watch me?
- They want Meeting prep first.
- They want project facts (blocked tickets, slipped milestones, budget burn, unanswered client emails), not named people.
- They want private warnings, a "this was wrong" button that works, and written limits on log use and retention.
- They want flat, cancellable prices. The agency owner wants a one-agent starter plan, setup in an afternoon, and briefs sent to email or Slack.

**Enterprise leaders** asked: does it scale, is it secure, what does it cost, how do we pilot?
- They want real data from one unit and a named accountable owner. They also want success bars and measured cost at scale.
- They want formal evidence: a pen test, data-flow documents, a validation package, references and continuity terms.
- They want different things on autonomy. Logistics, shared-services and the industrial CEO want some auto-approval. Bank, pharma and the IT buyer do not.
- They want pricing per unit, store, depot or agent, with caps. Some want a share of verified savings.

**Where they agree:** both groups want no individual scoring, hard cost caps and real-data proof.

**Where they split:** everyday users want warnings kept private. The industrial CEO wants shared numbers so that bad news is not softened.

## The best ideas suggested

- Run Project risk on project signals only. Drop "silence" or make it opt-in. Report at team level with a minimum group size.
- Let every employee see every log entry that names them. Block project output from reaching appraisal or redundancy processes by technical means, not just policy.
- Make Hiring forecast a standalone agent that reads only unit-level data.
- Make every flag link to its source rows and the rule that fired. Show in the log that explanation text never changes a figure.
- Let the email-reading agent hold no tools that change anything. Use constrained output fields. Show approvers the raw source text. Enforce client scoping at the data layer.
- Run a blind evaluation on redacted real data. People outside the build team should label or inject the problems and keep the answer key hidden. Report precision and recall with confidence intervals, and the share of explanation claims that trace to a cited record.
- Inject seeded errors into the approval queue. Track approval time and rate.
- Use tiered autonomy by amount and reversibility. Low-value, reversible items could clear with sampled audits. Anything touching pay or payments waits for a person.
- Never let an approval lapse into a "yes".
- Run a shadow phase on real tickets. The agent drafts while the team works as usual.
- Build an exceptions agent for field events, with a cost cap per event.
- Show managers their own flags first. Compare stores, not people.
- Add per-run, per-day and per-store caps with monthly cost reports. Offer source-code escrow, a named maintainer and a year-three price.

## Objections and how to answer them

| Objection | Suggested answer |
|---|---|
| "Dummy-data scores prove nothing." | Agree. Call them unit tests. Offer a blind, pre-registered evaluation on redacted real data and publish the results either way. |
| "This is surveillance." | Remove per-person signals and "silence". Add the employee self-view, written purpose limits, fixed log retention and agreement from staff representatives before launch. |
| "Prompt injection will get through." | Describe the architecture, not the intention. The reading agent has no change tools, scoping sits in the data layer, and approvers see raw text. Publish an adversarial test and its failure rate. |
| "Approvals will become a bottleneck." | Offer tiers by value and reversibility, with sampled audits and a named owner for the sampling rate. Keep approval-first for money and pay. |
| "Model cost is unknown." | Measure it in the pilot. Put caps in code per run, per day and per store or unit, and report monthly. |
| "Who maintains it?" | Name maintainers per connector. Offer escrow, a support contact and a year-three price. |
| "Where does the data go?" | Provide a data-flow and residency document, a tamper-evident exportable log and a deletion plan. |
| "A 150-line runtime means you own every vulnerability." | The loop is easy to audit. Show tests for the real risk layer: permissions, client-area enforcement and budget checks. Add a versioning and change-control policy. |
| "The pilot will die like others." | Agree the success bar, the expansion date and one accountable executive before starting. |

## Pricing and pilot signals

**Pricing.** Nearly everyone rejected per-seat pricing. Their reasons were that it rewards watching more people, and that agent cost follows event volume, not headcount.

- **Small agency:** a flat, cancellable monthly fee with a hard cap, roughly the cost of a project-tool seat bundle.
- **Project teams:** a flat fee per project or per CSM.
- **Finance and HR:** a flat fee per department or per agent, with a fixed number of runs, a hard cap and a monthly cost report.
- **Large groups:** a fixed fee per unit, per agent or per department, with a capped pass-through of model cost. The industrial CEO also suggested a share of verified savings. The IT buyer wants a fixed year-three price.
- **Retail:** a low flat fee per store per month with a cap.
- **Logistics:** a fee per depot, plus a small charge per exception, later tied to savings.
- **Shared services:** a fee per resolved ticket plus a small platform fee, with a monthly cap.
- **Bank and pharma:** a fixed annual platform fee plus a capped per-run charge. Security and validation support should be included, not billed as extras.

**Pilot shapes asked for:**
- **Agency:** a free or cheap 30-day trial on one real client.
- **CSM:** about 8 weeks on 2 or 3 projects.
- **Retail:** 5 or 6 stores for one quarter, with false-alarm limits agreed first.
- **Logistics:** one quarter in 3 cities, with baselines for exceptions, escalations and cost per shipment.
- **Industrial group:** one unit for a quarter, a success bar in rupees, and automatic rollout to 5 more units if it is met.
- **Finance:** read-only on closed ledger data, compared with past audit findings.
- **IT buyer:** 90 days on finance watch and meeting prep, with adoption targets and an exit clause.
- **Bank:** one read-only agent on synthetic data, after a pen test and with the regulator informed.
- **Pharma:** read-only, with a signed quality agreement and a validation plan.

## Recommended next steps for Company OS

1. **Reshape Project risk.** Use project facts only, aggregate to team level, and drop or opt-in "silence". Add the employee self-view, a written purpose limit, fixed retention, and a technical block on appraisal use.
2. **Lead with low-risk, read-only agents.** Start with Meeting prep, Finance watch and Hiring forecast (unit-level only). Keep Client requests for later.
3. **Build the evidence.** Create an eval harness on redacted real data with a hidden answer key. Report precision, recall, false alarms and explanation-citation rate. Add seeded-error tests for approvers.
4. **Prove the guardrails.** Publish tests showing a cross-client read fails and an injected message cannot trigger a tool. Use constrained fields and show raw source text in approvals.
5. **Measure and cap cost.** Set per-run, per-day and per-unit caps. Test a noisy trigger. Publish the real model cost at scale.
6. **Write the trust documents.** Prepare a data-flow and residency sheet, a tamper-evident log export and a data-never-read list. Add versioning and change control, escrow, a named maintainer and a pen test.
7. **Create a small-agency starter plan.** One or two agents, delivered by email or Slack, with setup in an afternoon and a cancellable flat fee.
8. **Design tiered autonomy.** Use value and reversibility tiers with sampled audits, and keep approval-first for money and pay. Treat a field-events exceptions agent as a separate later product.
9. **Run pilots with agreed terms.** Set the success bar, stop criteria, the accountable owner and a staff communication plan before starting. Include staff representatives.
10. **Start with two pilots.** A read-only finance pilot and a retail store pilot looked the most winnable.

## Quotes

- "But I am tired of pilots that prove something on dummy data and then die." (CEO, enterprise)
- "Silence is what a good day looks like when I'm stuck on a hard bug." (Senior developer, everyday)
- "If an overdue invoice flag comes from a rule, I can trace it to a number in the ledger." (Finance manager, everyday)
- "If it cries wolf, I stop reading it." (Project manager and CSM, everyday)
- "If setup takes more than an afternoon, I won't do it." (Small agency owner, everyday)
- "Price it per store, cheaply, or it dies at 300." (Chief Operating Officer of a retail chain, enterprise)
- "My default answer is no, and this pitch hasn't changed it." (Chief Information Security Officer of a bank, enterprise)
- "In the field, waiting for approval at 2 a.m. is the same as doing nothing." (VP Operations of a logistics company, enterprise)
- "That is a demo, not evidence." (Head of Procurement at a pharma company, enterprise)
- "If people approve 99 percent in seconds, you have a rubber stamp, not a control." (AI researcher and sceptic, critic)
- "Consent that is demanded by the employer isn't real consent, so staff groups should be consulted before any pilot starts." (Privacy and workers' rights advocate, critic)
- "Nobody opened the inbox after month two." (Enterprise IT buyer, critic)
