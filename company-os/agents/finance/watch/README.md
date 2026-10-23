# Finance watch

Every day this agent reads DevX's books and tells the finance lead, in private, about money that needs a look.
It does not move money. It points at the problem, gives the evidence and suggests a next step.

## What it watches

| Situation | What triggers it | Example in the dummy company |
|---|---|---|
| Duplicate invoice | Same vendor and same amount within 10 days | SkyWay Travel Desk, INV051 and INV054, INR 132,500 |
| New vendor paid a lot | A payment over 5 lakh INR to a vendor created under 30 days before | Nova Edge Consulting, PAY030, INR 680,000 |
| Budget overrun | A team's spend in a month and category goes above its budget | Design, hardware, August 2026 |
| Travel share of salary | A team's travel in a month is over 20% of its total monthly salaries | Growth, September 2026 |

It stays quiet about look-alikes: a monthly subscription with the same amount each month (about 30 days apart),
and a large payment to an old vendor, such as a yearly prepayment.

## When it acts

Once a day, on a timer. The finance lead or the CEO can also run it on request. A duplicate or a large payment is
news for 14 days after it happens. An overrun or travel share shows every day while it is still true for the month.
If nothing needs a look, it sends nothing and makes no model call.

## Who it tells

- The finance lead gets every finding, in one private message.
- The CEO also gets the travel finding.
- Nobody outside DevX gets a message.

## What the finance lead receives

One message per run. For each finding:

1. What it is, with the invoice, payment or team ids and the amount.
2. Evidence: the vendor, dates, amounts and gap in days (or the budget, spend and share).
3. Why it matters, in one sentence.
4. A next step.

For a likely duplicate or a risky new-vendor payment the agent may also propose a follow-up task, such as
"Hold payment of INV054 until checked against INV051". The follow-up waits in the approvals list.
The finance lead or the CEO decides. Nothing is written until they approve.

## What it may never do

- Show one person's salary. It uses team totals only, and teams under 3 people show no salary at all.
- Pay, hold or change anything in the books. It only reads them.
- Write a follow-up without approval.
- Message anyone who is not a DevX person.
- Use a tool outside its list, or read any area other than `devx-internal`.

## Tools

| Tool | Use | Needs approval |
|---|---|---|
| `invoices_window` | Invoices in the last days | No |
| `payments_window` | Payments with the vendor's age at payment | No |
| `budget_vs_spend` | Budget, spend and over-budget flag per team, month and category | No |
| `travel_share_of_salary` | Travel spend against team salary total | No |
| `send_private_message` | Private message to the finance lead or the CEO | No |
| `create_followup_task` | Follow-up task in company memory | Yes |

## How the run works

Read the books, then code finds the cases, so the numbers are exact. The model only explains them. Before anything
is sent, a check confirms every id and amount is one the code found, and that no single salary appears. Then
the messages go out, the follow-ups wait for approval, and each case is saved to memory.

## Who may start it

Finance lead, CEO, and the system timer. Other roles, such as engineers, are refused.

## How it is scored

`replay_exam.py` replays the planted cases. For each one, it runs the agent as of the first day a simple rule could
see it. Score: cases found, cases missed, and false alarms (a look-alike flagged). Current result: 8 of 8 found,
0 false alarms. Scores are saved with `memory.add_score`. Run it with `python3 -m agents.finance_watch.replay_exam`.

## Files

`pack.py` (the agent), `fake_brain.py` (stand-in for the model), `replay_exam.py` (the exam), tests in
`tests/test_agent_finance_watch.py`.
