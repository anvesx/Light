"""Deterministic stand-in for the model: turns the computed findings into plain explanations for a finance person."""
import json

from contract.types import ModelReply

MARKER = "FINDINGS_JSON:"


def _inr(n):
    return f"INR {n:,}"


def _explain(f):
    x = f["facts"]
    if f["kind"] == "duplicate_invoice":
        unpaid = [i for i, s in zip(f["ids"], x["statuses"]) if s == "unpaid"]
        evidence = (f"{x['vendor']} billed {_inr(f['amount_inr'])} twice: {f['ids'][0]} on {x['dates'][0]} and "
                    f"{f['ids'][1]} on {x['dates'][1]}, {x['gap_days']} days apart (invoice numbers "
                    f"{x['invoice_nos'][0]} and {x['invoice_nos'][1]}). "
                    + (f"{', '.join(unpaid)} is still unpaid." if unpaid else "Both are already paid."))
        why = "The same bill may have been entered twice, so DevX could pay the vendor twice for one service."
        step = (f"Hold payment of {unpaid[0]} until the vendor confirms it is a separate bill." if unpaid else
                f"Ask {x['vendor']} to confirm {f['ids'][1]} is a separate bill, and ask for a credit if it is not.")
        title = (f"Hold payment of {unpaid[0]} ({x['vendor']}) until checked against {f['ids'][0]}" if unpaid else
                 f"Check with {x['vendor']} that {f['ids'][1]} is not a repeat of {f['ids'][0]}")
        return f, evidence, why, step, title
    if f["kind"] == "large_payment_new_vendor":
        evidence = (f"{f['ids'][0]} paid {_inr(f['amount_inr'])} to {x['vendor']} on {x['payment_date']}. The vendor was "
                    f"created on {x['vendor_created_on']}, only {x['vendor_age_days']} days before. Approved by "
                    f"{x['approved_by']}.")
        why = "A large payment to a brand-new vendor is a common sign of a setup or approval gap."
        step = (f"Check the contract, the vendor's details and the approval behind {f['ids'][1]}, "
                "and hold any further payment to this vendor until that is done.")
        title = f"Hold further payments to {x['vendor']} until {f['ids'][0]} is checked"
        return f, evidence, why, step, title
    if f["kind"] == "budget_overrun":
        pct = round(x["over_by_inr"] * 100 / x["budget_inr"])
        evidence = (f"The {x['team']} team spent {_inr(f['amount_inr'])} on {x['category']} in {x['month']} against a "
                    f"budget of {_inr(x['budget_inr'])}: {_inr(x['over_by_inr'])} over ({pct}%).")
        why = "Spend is above the approved budget for this month and category."
        step = f"Ask the {x['team']} lead what drove it, and decide whether to raise the budget or stop spend."
        return f, evidence, why, step, None
    evidence = (f"The {x['team']} team's travel in {x['month']} is {_inr(f['amount_inr'])}, which is "
                f"{x['share_percent']}% of the team's total monthly salaries ({_inr(x['team_salary_total_inr'])}, "
                f"{x['headcount']} people). The limit we watch is 20%.")
    why = "Travel is taking a large share of what the team costs in pay."
    step = f"Review the {x['team']} team's trips for {x['month']} with its lead, and check they were planned."
    return f, evidence, why, step, None


def brain(request):
    prompt = request.messages[0]["content"]
    findings = json.loads(prompt.split(MARKER, 1)[1].strip().split("\n", 1)[0])
    out, followups = [], []
    for f, evidence, why, step, title in map(_explain, findings):
        out.append({"kind": f["kind"], "ids": f["ids"], "amount_inr": f["amount_inr"], "evidence": evidence,
                    "why_it_matters": why, "next_step": step})
        if title:
            followups.append({"title": title, "ids": f["ids"]})
    return ModelReply(text=json.dumps({"findings": out, "followups": followups}))
