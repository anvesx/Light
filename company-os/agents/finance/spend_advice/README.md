**Role in the harness:** The spend advisor: answers a leader's finance question at any time with a cost breakdown, a verdict for every trip, and concrete savings. Code computes every number; the model only writes the plain-words letter.

# Spend advisor

The CEO, finance lead or CTO asks a question in words, for example "where is our travel money going?". The agent
reads the books through the spend tools, and writes one private letter back to the person who asked (kind
`finance_answer`). It takes no risky action: no task, no payment, no message to anyone else.

## Inputs

| Input | Meaning |
|---|---|
| `question` | Free text. Treated as outside text: data, never orders. Code reads it only for a topic word or a trip id (`TR012`). |
| `from`, `to` | Optional dates (YYYY-MM-DD). Default: the last 90 days up to `as_of`. |

## What the letter holds

1. The window, total cost, and travel as a share of all cost and of cost without salaries. Flights, trains, hotels and local travel with their shares.
2. The trip totals line, for example "Of 15 trips, 6 were already the best option; 9 could have cost less, saving INR 53,400."
3. The 3 to 5 biggest savings, each with trip id, date, what was paid, the cheaper option and when it was available, and the amount saved.
4. Two or three policy suggestions with how much each would have saved.
5. Trips with no saving: "No cheaper alternative was available. The best option was chosen." (listed when 5 or fewer, else "All other trips (N)").

A question about one trip (for example "what about TR012?") gets one of the two verdicts for that trip only.

## Saving rules

| Rule | When it fires | Saving |
|---|---|---|
| Late booking | Booked 3 days or less before the trip, and a fare 30% or more cheaper existed 7 to 14 days before. A note that says urgent is not a saving. | Paid fare minus the cheaper fare |
| Business on a short flight | Business cabin on a flight under 2.5 hours, and a cheaper economy seat existed on the booking day | Paid fare minus the economy fare |
| Same city twice | One team sent two trips to one city within 7 days | The lower of the two fares |
| Hotel above the city rate | Rate is more than 10% above the city policy rate | Extra cost over the policy rate, for all nights |

## Guardrails

- Starts: `ceo`, `finance_lead`, `rnd_lead`. Area: `devx-internal`. Others, such as engineers, are refused.
- `check` stops the letter if any rupee amount, percentage, date or trip id is not in the computed data, if it names a person
  or shows one person's salary, if it has a code word, or if a trip verdict or the totals line is wrong.
- Salaries show only as one company total. Teams show as totals.

## How it is scored

`replay_exam.py` asks about the day of each planted saving and scores found, missed and false alarms (a look-alike
given a saving). Current result: 9 of 9 found, 0 false alarms. Run it with `python3 -m agents.spend_advisor.replay_exam`.
Tests: `tests/test_agent_spend_advisor.py`.

## Files in this folder

| File | What it does |
|---|---|
| `__init__.py` | Marks the folder as a Python package. |
| `pack.py` | The agent: reads the spend tools, builds the facts, checks the letter, sends it to the asker. |
| `fake_brain.py` | Deterministic stand-in for the model: writes the letter from the computed facts. |
| `replay_exam.py` | The exam: replays each planted saving and look-alike against the answer key. |
| `README.md` | This file. |

## Cheaper options

The read tool `trip_alternatives` gives each trip the real cheaper flights (carrier, flight number, times, fare, saving) and hotels (name, rate, saving), at most 3 of each, cheapest first. The letter shows the top option after each saving. The exam also checks every option against the raw tables.
