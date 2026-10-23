"""Read tools for DevX books: invoices, payments with vendor age, budgets against spend, travel share of salary."""
from .tool_reply import ToolInputError, build_tool, days_before, days_between, int_arg, str_arg

AREA = "devx-internal"
MIN_TEAM_FOR_SALARY = 3   # smaller teams would reveal one person's pay


def _ok(area_id):
    return area_id == AREA


def _month(args, as_of):
    month = str_arg(args, "month") or as_of[:7]
    if len(month) != 7 or month[4] != "-":
        raise ToolInputError("month must look like YYYY-MM")
    return month


def make_invoices_window(data_conn):
    def handler(args, area_id, as_of, ctx):
        since, limit = days_before(as_of, int_arg(args, "days", 60, 1, 365)), int_arg(args, "limit", 80, 1, 200)
        sql = ("SELECT i.invoice_id, i.vendor_id, v.name AS vendor, i.invoice_no, i.amount_inr, i.date, i.project_id, "
               "i.status FROM invoices i JOIN vendors v ON v.vendor_id = i.vendor_id WHERE i.date > ? AND i.date <= ?")
        params = [since, as_of]
        if str_arg(args, "vendor_id"):
            sql, params = sql + " AND i.vendor_id = ?", params + [args["vendor_id"]]
        rows = data_conn.execute(sql + " ORDER BY i.date, i.invoice_id LIMIT ?", params + [limit]).fetchall()
        return {"as_of": as_of, "from_exclusive": since, "invoices": [dict(r) for r in rows]}
    return build_tool(
        "invoices_window", "Invoices dated in the last `days` (default 60) up to as_of, with vendor, amount, status. "
        "Optional vendor_id.", {"days": {"type": "integer"}, "vendor_id": {"type": "string"}, "limit": {"type": "integer"}},
        handler, area_ok=_ok, area_label=AREA)


def make_payments_window(data_conn):
    def handler(args, area_id, as_of, ctx):
        since, limit = days_before(as_of, int_arg(args, "days", 60, 1, 365)), int_arg(args, "limit", 80, 1, 200)
        min_amount = int_arg(args, "min_amount_inr", 0, 0, 10**12)
        rows = data_conn.execute(
            "SELECT p.payment_id, p.invoice_id, p.vendor_id, v.name AS vendor, v.created_on AS vendor_created_on, "
            "p.amount_inr, p.date, p.approved_by FROM payments p JOIN vendors v ON v.vendor_id = p.vendor_id "
            "WHERE p.date > ? AND p.date <= ? AND p.amount_inr >= ? ORDER BY p.date, p.payment_id LIMIT ?",
            (since, as_of, min_amount, limit)).fetchall()
        out = [{**dict(r), "vendor_age_days": days_between(r["date"], r["vendor_created_on"])} for r in rows]
        return {"as_of": as_of, "from_exclusive": since, "payments": out}
    return build_tool(
        "payments_window", "Payments in the last `days` (default 60) up to as_of, with vendor age in days at payment. "
        "Optional min_amount_inr.", {"days": {"type": "integer"}, "min_amount_inr": {"type": "integer"},
                                     "limit": {"type": "integer"}}, handler, area_ok=_ok, area_label=AREA)


def make_budget_vs_spend(data_conn):
    def handler(args, area_id, as_of, ctx):
        month, team = _month(args, as_of), str_arg(args, "team")
        spend = {(r["team"], r["category"]): r["s"] for r in data_conn.execute(
            "SELECT team, category, SUM(amount_inr) AS s FROM expenses WHERE substr(date, 1, 7) = ? AND date <= ? "
            "GROUP BY team, category", (month, as_of))}
        rows = []
        for b in data_conn.execute("SELECT * FROM budgets WHERE month = ? ORDER BY team, category", (month,)):
            if team and b["team"] != team:
                continue
            s = spend.get((b["team"], b["category"]), 0)
            if s == 0 and not args.get("include_zero"):
                continue
            rows.append({"team": b["team"], "month": month, "category": b["category"], "budget_inr": b["amount_inr"],
                         "spend_inr": s, "over_budget": s > b["amount_inr"]})
        rows.sort(key=lambda r: (not r["over_budget"], r["team"], r["category"]))
        return {"as_of": as_of, "note": "spend counted up to as_of; budget is for the full month", "rows": rows}
    return build_tool(
        "budget_vs_spend", "Per team, month and category: budget, spend to as_of and an over_budget flag. "
        "Rows with zero spend are left out unless include_zero.", {"month": {"type": "string"}, "team": {"type": "string"},
                                                                   "include_zero": {"type": "boolean"}},
        handler, area_ok=_ok, area_label=AREA)


def make_travel_share_of_salary(data_conn):
    def handler(args, area_id, as_of, ctx):
        month = _month(args, as_of)
        rows = []
        for t in data_conn.execute(
                "SELECT team, COUNT(*) AS n, SUM(monthly_salary_inr) AS pay FROM people WHERE is_devx = 1 "
                "GROUP BY team ORDER BY team"):
            travel = data_conn.execute(
                "SELECT COALESCE(SUM(amount_inr), 0) FROM expenses WHERE team = ? AND category = 'travel' "
                "AND substr(date, 1, 7) = ? AND date <= ?", (t["team"], month, as_of)).fetchone()[0]
            big = t["n"] >= MIN_TEAM_FOR_SALARY
            rows.append({"team": t["team"], "month": month, "headcount": t["n"], "travel_spend_inr": travel,
                         "team_salary_total_inr": t["pay"] if big else None,
                         "travel_share_of_salary": round(travel / t["pay"], 3) if big and t["pay"] else None})
        return {"as_of": as_of, "note": f"teams under {MIN_TEAM_FOR_SALARY} people show no salary or share",
                "rows": rows}
    return build_tool(
        "travel_share_of_salary", "Per team for a month: travel spend to as_of, team salary total and travel share of it. "
        "Team totals only.", {"month": {"type": "string"}}, handler, area_ok=_ok, area_label=AREA)


def books_tools(data_conn):
    return [make_invoices_window(data_conn), make_payments_window(data_conn), make_budget_vs_spend(data_conn),
            make_travel_share_of_salary(data_conn)]
