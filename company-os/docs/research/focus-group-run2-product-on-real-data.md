> Simulated opinions from one AI model role-playing 16 personas; useful for ideas and objections, not proof of demand.

## Summary

Sixteen fictional people discussed Company OS: five everyday users, eight enterprise leaders and four critics (one counted in each group below as listed in the transcript). Almost everyone said "maybe". Two said no as designed: the bank security chief (no for production, maybe for a fenced pilot) and the privacy advocate (no, until staff-facing controls exist). Nobody said a clear yes.

The pull is real. People want source-linked findings, rules in plain code, and read-only access. Finance watch was the most named first pick. Meeting prep and Hiring forecast also drew strong interest.

The fear is also real. Project risk and Store watch worry people most, because they can feel like staff monitoring. Approval fatigue was raised by almost everyone. Many said it makes the human gate weak. Prompt injection and cross-client leaks came up often as well.

Enterprise leaders asked for more than the pitch offers. They want agents that resolve work, tiered autonomy, validation papers, in-country hosting and named owners. Small users want a cheap, flat, one-afternoon setup.

## What people agree is right

- **Rules in code, AI only explains.** Finance, engineering and critic voices liked that most findings come from clear rules. It keeps cost flat and makes findings testable.
- **Every finding links to its source record.** Auditors, finance leads and HR leads all said this is what makes a finding usable.
- **Read-only connectors and human approval as a start.** Most accepted these for a first pilot.
- **Finance watch as the safest first agent.** Rohit, Karthik, Sheila, Ingrid, Deepak, Rekha, Vijay, Sana and the bank CISO (for a fenced pilot) all pointed to it or something close to it.
- **Meeting prep as a low-risk win.** Arjun, Kavita, Sana and Ingrid would start there.
- **Event triggers.** The logistics VP liked agents that act when something slips.
- **Small, auditable runtime.** Karthik and others liked it, though they asked who supports it.
- **Per-client memory areas, the pause switch and the audit log.** Seen as good ideas, but only if they are proven to work.

## What is wrong or risky

- **Project risk looks like staff monitoring.** "Hours, silence and staffing" was called surveillance by Arjun, Neha, Meenakshi, Zainab and Ingrid. "Silence" per person drew the hardest line.
- **Store watch judges people.** Ingrid, Zainab and Anil all warned that false flags on legitimate refunds would hurt trust and morale.
- **Approval fatigue.** Raised by Arjun, Farhan, Karthik, Sheila, Ingrid, Rekha, Vijay and others. Ingrid added that approvals then count as false proof of checking.
- **Prompt injection is a claim, not a control.** "Outside text is data" was called unproven by Farhan and Karthik. The Client requests agent worries them most, since it reads passwords and untrusted text.
- **Shared memory can leak or drift.** Client data can cross areas through summaries. Billing or risk data can drift into appraisals and discipline.
- **The audit log protects the company, not staff.** Zainab and others said staff cannot see what is logged about them.
- **Links do not prove the explanation is right.** Ingrid and Rohit said AI wording can drift from the record. Rohit wants figures pulled from the record, never paraphrased.
- **Connector and ownership risk.** Sheila and Deepak said connectors break quietly after vendor updates, and a small vendor may leave an orphan tool.
- **Watch, not work.** Rekha and Lakshmi said the agents advise but do not take work off queues.
- **Built for an office.** Lakshmi said depot, driver and tracker systems are missing.
- **Too heavy for small firms.** Sana said eight agents and consoles suit a 150-person firm, not 15 people.
- **Regulated industries need validation.** Deepak listed qualification, change control and reproducibility. Model output that changes between runs is a validation problem.
- **Headcount story.** Rekha and Vijay raised staff fear of job loss and the fate of middle managers.

## Everyday users vs big enterprise (how they differ)

**Everyday users** ask: will this help me or watch me?
- They want time back: less status chasing, fewer surprise client calls, fewer late invoices.
- Their main fear is being measured or blamed. Arjun, Kavita and Neha all asked who can read the log.
- They want project-level wording, never per-person. They want to see what is logged about themselves.
- They want one-click "wrong" feedback and a shown false-alarm rate.
- Small agency owner Sana wants a flat price, a hard cap and setup in an afternoon. She would skip Project risk.
- Rohit wants the rule, fields and numbers first, with AI prose second.

**Big enterprise leaders** ask: does it scale, is it secure, what does it cost, how do we pilot it?
- They worry about the approval queue becoming a new layer. They want tiered autonomy with cost caps (Vijay, Lakshmi, Rekha).
- They want the agents to resolve work, not only warn (Rekha, Lakshmi).
- They need security and compliance proof: in-country hosting, SIEM export, tamper-evident logs, least privilege (Farhan), validation papers (Deepak), works council agreements (Meenakshi).
- They want pricing per unit, store, depot, department or case, not per seat.
- They want tight pilots with a named owner, a deadline and agreed numbers.
- Their needs differ by industry. Retail wants store leakage. Logistics wants exceptions from depot systems. Pharma wants validation. A shared-services centre wants volume.

**Where they agree:** both groups want project-level or team-level data only, a staff-visible log, measured false-positive rates and no per-seat pricing.

## The best ideas suggested

1. **Aggregation built into the connector.** Hiring forecast uses team-level data with a minimum group size and small-group suppression, with no individual rows (Neha, Meenakshi, Zainab). Add attrition at the same level.
2. **Staff view of their own log.** Every entry that names a person is visible to them, with source, purpose and who read it (Zainab, Arjun, Neha).
3. **Purpose limits enforced in code.** Billing and risk data cannot be reused for appraisal or discipline. Add worker representatives and written agreements.
4. **Tiered autonomy.** Low-risk actions run alone under a cost cap, with sampling. High-risk actions need approval (Vijay, Karthik, Lakshmi, Rekha).
5. **Seeded bad findings.** Plant known-bad items in the approval queue to test whether approvers check (Karthik).
6. **Published precision per agent.** Measure on real labeled cases monthly. Sample approved items against source records. Do not treat approval rate as accuracy (Ingrid, Karthik).
7. **Approver reports.** Click-through and approval-rate per approver, reviewed monthly by a named owner (Sheila).
8. **Connector health checks.** Alert when a feed goes silent (Sheila).
9. **Limits at the tool layer.** Per-agent allowlists, per-client read scopes checked in code, no outbound channel for agents reading untrusted text (Karthik, Farhan).
10. **Rule first, prose second.** Show the rule, fields and numbers first. Prose carries only record figures (Rohit).
11. **Warning wording and feedback.** "Hours are 30 percent over plan", never "this person went quiet". Show how often similar warnings were right, with a one-click "wrong" (Kavita).
12. **Pre-approved playbooks.** For example, rebook a vendor under a cost cap (Lakshmi).
13. **Tenant-style deployment.** Run in the buyer's own environment with a red-team test before live data (Farhan).
14. **Small-agency bundle.** Finance watch and Delivery progress only, flat price, one-afternoon setup (Sana).
15. **Owner for the log.** A named person independent of HR audits who reads the audit log (Neha).

## Objections and how to answer them

| Objection | Suggested answer |
|---|---|
| "This is employee monitoring." | Make project-level and team-level the only mode. Enforce it in the connector. Drop per-person hours and silence. Give staff a view of their own entries. Agree scope with worker representatives first. |
| "Approval becomes a rubber stamp." | Use tiers. Sample approved items. Seed bad findings. Report per-approver rates. Never use approval rate as proof of accuracy. |
| "Prompt injection will get through." | Enforce limits in code at the tool layer. Give agents that read untrusted text no outbound channel. Run an adversarial test on the buyer's own records and share the results. |
| "Shared memory will leak across clients or units." | Check read scope in code on retrieval. Test cross-area retrieval adversarially. Keep summaries inside the area. |
| "Who supports this in year three?" | Offer a named support contract, connector tests, a rule-change process, health checks and written exit terms for memory and log export. |
| "AI text may misstate the record." | Show rule, fields and source first. Allow only figures pulled from the record in the prose. Sample explanations against records. |
| "Agents only watch, they do not work." | Plan routine-case resolution with approval by exception and a measured error rate per case type. Be honest that this is not built yet. |
| "The pitch is for offices." | Add connectors for depot, driver, tracker and vendor feeds. Pick one exception type for a first pilot. |
| "Too complex for a small agency." | Offer a two-agent bundle, vendor-run setup and connector fixes, and a flat capped price. |
| "Regulated industries need validation." | Prepare a validation package: qualification file, change control for model, prompt and connector updates, data integrity audit trail, references. Keep it read-only. |
| "Staff will see this as a headcount play." | Prepare an open story and tell staff before any pilot. Keep the agent at team and queue level. |
| "A pilot will die in committee." | Agree one unit, a hard deadline, a named owner and success numbers in advance. Pre-agree rollout if targets are met. |

## Pricing and pilot signals

**Pricing, nearly all agreed on:**
- No per-seat or per-employee pricing. Several said it feels like paying to track people. Logistics and retail also said most staff never log in.
- Flat and capped AI usage, so cost is predictable (Rohit, Karthik, Sheila, Farhan, Deepak).
- Units differ by buyer:
  - Small agency: flat monthly fee, hard cap, cheap enough that one saved afternoon pays for it (Sana).
  - Per active client project (Kavita) or per active agent (Arjun, Neha, Karthik).
  - Per business unit with outcome-linked fees (Vijay).
  - Per store, low, with a pilot premium (Anil).
  - Per depot or workflow (Lakshmi).
  - Per resolved case or queue, tied to accuracy (Rekha).
  - Per department per year (Sheila, Deepak, Farhan, Ingrid).
- Support, validation, audit and exit terms should be priced visibly and included, not hidden extras (Deepak, Sheila, Farhan, Zainab on staff transparency in base tier).
- Ingrid does not want pricing per finding, so no one is rewarded for more alerts.

**Pilot conditions, common patterns:**
- **Finance watch only, read-only, real records, 60 to 90 days:** Rohit, Karthik, Sheila, Farhan (fenced), Ingrid (with Meeting prep), Deepak (indirect spend, non-GxP).
- **Meeting prep and Client requests, Project risk off:** Arjun.
- **Hiring forecast only, aggregated:** Neha, Meenakshi (one or two units, one country, after impact assessment and works council agreement).
- **Retail:** five or six stores for one quarter, findings to the regional manager first, compared with similar stores (Anil). He would stop below about half of flags confirmed real.
- **Logistics:** one region, one exception type, with cost per shipment and escalation count against baseline (Lakshmi).
- **Shared services:** one or two case types, accuracy per case type and review load inside SLA (Rekha).
- **Enterprise group:** one unit, hard 90-day deadline, named executive owner, pre-agreed numbers (Vijay).
- **Small agency:** one-month low fixed price, vendor does setup, walk away if no real unbilled hours or late invoices are found (Sana).
- Pilots should have a named accuracy owner, a fixed end date and exit criteria agreed in advance.

**Switch-off triggers named most often:**
- Any person-level finding used in appraisal, discipline or ranking.
- Any cross-client or cross-area leak.
- False flags too high for teams to review.
- Approvals near 100 percent with no sign of checking.
- Gaps or tampering in the audit log.
- Silent change to a model, prompt or connector.
- Cost over the cap.

## Recommended next steps for Company OS

1. **Lead with Finance watch.** It is the most agreed first pick, rules-based and has a clear owner. Pair it with Meeting prep for a second, low-risk entry.
2. **Rework Project risk before showing it to anyone.** Project-level only, no per-person hours, silence or chat. Keep it out of early pilots with worker-sensitive buyers.
3. **Build the staff view of the audit log.** Each person sees entries that name them, with source, purpose and who read it. Add purpose limits enforced in code and retention rules.
4. **Enforce aggregation in the Hiring forecast connector.** Minimum group size, suppression, no individual rows.
5. **Move safety controls to the tool layer.** Allowlists, per-client read scopes in code, no outbound channel for agents that read untrusted text. Run and share an adversarial test.
6. **Fix the approval design.** Define autonomy tiers with cost caps. Add sampling, seeded bad findings and per-approver reports. Do not use approval rate as evidence of accuracy.
7. **Publish precision per agent monthly.** Measure on the buyer's real labeled records. Name a person who owns it.
8. **Show rule and figures first in the console.** Keep AI prose secondary and limited to record figures. Add one-click "wrong".
9. **Add connector health checks and a rule-change process.** Plan a named support contract and exit terms for the shared memory and logs.
10. **Prepare buyer packs.**
    - Security: in-country hosting, per-agent identities, tamper-evident log export to a SIEM, change ownership for model and prompt.
    - Regulated: validation package and references.
    - Small agency: a two-agent bundle with a flat capped price and vendor-run setup.
11. **Decide the next product bets honestly.** The Travel booking, Learning loop and chief-of-staff ideas did not come up much. The louder asks were routine-case resolution with approval by exception, and connectors for operations systems such as depot and vendor feeds.
12. **Offer a standard pilot template.** One unit, a named owner, a fixed end date and agreed success numbers.

## Quotes

- "I'd switch it off the day any output is used to rank or question individuals. Approval-only is a good start, but people stop reading approvals fast." (Senior developer, everyday user)
- "If it flags every quiet week as a risk, I'll start ignoring it, and then the one real warning gets missed." (Project manager and CSM, everyday user)
- "I'd want the rule, the inputs and the numbers shown first, with the prose clearly secondary." (Finance manager, everyday user)
- "If I'm the only approver, I'm just clicking yes all day. That's a new chore, not a saved one." (Owner of a small design and web agency, everyday user)
- "At our scale that becomes thousands of approvals in a queue, and the queue becomes the new layer." (CEO of a large industrial group, enterprise leader)
- "Trust is slow to build and quick to lose." (Chief Human Resources Officer, enterprise leader)
- "'Text from outside is treated as data' is a claim, not a control." (Chief Information Security Officer at a bank, enterprise leader)
- "In my world the trouble is a truck broken down outside a city, a depot short of drivers at 5 a.m., or a vendor who didn't show." (VP Operations at a logistics company, enterprise leader)
- "Staff will read this as a headcount play whatever you say. You need a story for that before any pilot." (Head of a shared-services centre, enterprise leader)
- "If the log says 'human verified', but nobody verified anything. Please don't count approvals as evidence of accuracy." (AI researcher and sceptic, critic)
- "A log that only managers and admins read is a record of staff, not protection for them." (Privacy and workers' rights advocate, critic)
- "I've shelved a dozen of these, and not one failed on technology. They failed because nobody owned them after the first quarter." (Enterprise IT buyer, critic)
