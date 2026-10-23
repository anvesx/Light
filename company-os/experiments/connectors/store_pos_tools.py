"""Read tools for the retail client's store POS: refunds, discounts and remakes by staff member."""
from collections import Counter

from .tool_reply import ToolInputError, build_tool, days_before, int_arg, retail_area_ids, str_arg


def _window(args, as_of, default=30):
    return days_before(as_of, int_arg(args, "days", default, 1, 365))


def _staff_names(conn):
    return {r["person_id"]: r["name"] for r in conn.execute("SELECT person_id, name FROM people WHERE client_id IS NOT NULL")}


def _area_ok(data_conn):
    return lambda a: a in retail_area_ids(data_conn)


def _store_filter(args, area_id, conn):
    store_id = str_arg(args, "store_id")
    if store_id and not conn.execute("SELECT 1 FROM stores WHERE store_id = ? AND client_id = ?", (store_id, area_id)).fetchone():
        raise ToolInputError(f"store {store_id!r} is not in area {area_id!r}")
    return store_id


def _rows(conn, table, date_col, area_id, since, as_of, store_id):
    sql = (f"SELECT t.* FROM {table} t JOIN stores s ON s.store_id = t.store_id WHERE s.client_id = ? "
           f"AND t.{date_col} > ? AND t.{date_col} <= ?")
    params = [area_id, since, as_of]
    if store_id:
        sql, params = sql + " AND t.store_id = ?", params + [store_id]
    return conn.execute(sql, params).fetchall()


def make_refunds_by_staff(data_conn):
    def handler(args, area_id, as_of, ctx):
        since, store_id, names = _window(args, as_of), _store_filter(args, area_id, data_conn), _staff_names(data_conn)
        rows = _rows(data_conn, "pos_refunds", "date", area_id, since, as_of, store_id)
        staff, stores = {}, {}
        for r in rows:
            s = staff.setdefault(r["staff_id"], {"staff_id": r["staff_id"], "name": names.get(r["staff_id"]),
                                                 "store_id": r["store_id"], "refunds": 0, "amount_inr": 0,
                                                 "by_method": Counter(), "by_reason": Counter()})
            s["refunds"] += 1
            s["amount_inr"] += r["amount_inr"]
            s["by_method"][r["method"]] += 1
            s["by_reason"][r["reason"]] += 1
            st = stores.setdefault(r["store_id"], {"store_id": r["store_id"], "refunds": 0, "staff": set(),
                                                   "by_method": Counter(), "by_reason": Counter()})
            st["refunds"] += 1
            st["staff"].add(r["staff_id"])
            st["by_method"][r["method"]] += 1
            st["by_reason"][r["reason"]] += 1
        out = sorted(staff.values(), key=lambda s: (-s["by_method"]["cash"], -s["refunds"], s["staff_id"]))
        for s in out:
            s["cash_refunds"] = s["by_method"]["cash"]
        for st in stores.values():
            st["distinct_staff"] = len(st.pop("staff"))
        return {"as_of": as_of, "from_exclusive": since, "staff": out[:int_arg(args, "limit", 20, 1, 60)],
                "stores": sorted(stores.values(), key=lambda x: x["store_id"])}
    return build_tool(
        "refunds_by_staff", "Refunds in the last `days` (default 30) per staff member (count, amount, cash count, method and "
        "reason breakdowns) and per store (with distinct staff). Optional store_id.",
        {"days": {"type": "integer"}, "store_id": {"type": "string"}, "limit": {"type": "integer"}}, handler,
        area_ok=_area_ok(data_conn), area_label="the retail client's area")


def make_discounts_by_staff(data_conn):
    def handler(args, area_id, as_of, ctx):
        since, store_id, names = _window(args, as_of), _store_filter(args, area_id, data_conn), _staff_names(data_conn)
        rows = _rows(data_conn, "pos_discounts", "date", area_id, since, as_of, store_id)
        staff, approvers = {}, {}
        for r in rows:
            s = staff.setdefault(r["requester_id"], {
                "staff_id": r["requester_id"], "name": names.get(r["requester_id"]), "store_id": r["store_id"],
                "discounts": 0, "self_approved": 0, "pct_total": 0, "otp_retries_total": 0, "approved_by": Counter(),
                "first_date": r["date"], "last_date": r["date"]})
            s["discounts"] += 1
            s["self_approved"] += r["requester_id"] == r["approver_id"]
            s["pct_total"] += r["pct"]
            s["otp_retries_total"] += r["otp_retries"]
            s["approved_by"][r["approver_id"]] += 1
            s["first_date"], s["last_date"] = min(s["first_date"], r["date"]), max(s["last_date"], r["date"])
            a = approvers.setdefault(r["approver_id"], {"approver_id": r["approver_id"], "approved": 0,
                                                        "requesters": set(), "first_date": r["date"], "last_date": r["date"]})
            a["approved"] += 1
            a["requesters"].add(r["requester_id"])
            a["first_date"], a["last_date"] = min(a["first_date"], r["date"]), max(a["last_date"], r["date"])
        out = sorted(staff.values(), key=lambda s: (-s["self_approved"], -s["discounts"], s["staff_id"]))
        for s in out:
            s["avg_pct"] = round(s.pop("pct_total") / s["discounts"], 1)
        for a in approvers.values():
            a["distinct_requesters"] = len(a.pop("requesters"))
        top = sorted(approvers.values(), key=lambda a: (-a["approved"], a["approver_id"]))[:5]
        return {"as_of": as_of, "from_exclusive": since, "staff": out[:int_arg(args, "limit", 20, 1, 60)],
                "top_approvers": top}
    return build_tool(
        "discounts_by_staff", "Discounts in the last `days` (default 30) per requesting staff member: count, self-approved "
        "count, average percent, OTP retries, who approved, date range; plus the top approvers. Optional store_id.",
        {"days": {"type": "integer"}, "store_id": {"type": "string"}, "limit": {"type": "integer"}}, handler,
        area_ok=_area_ok(data_conn), area_label="the retail client's area")


def make_remakes_by_staff(data_conn):
    def handler(args, area_id, as_of, ctx):
        since, store_id, names = _window(args, as_of), _store_filter(args, area_id, data_conn), _staff_names(data_conn)
        rows = _rows(data_conn, "alterations", "date", area_id, since, as_of, store_id)
        staff = {}
        for r in rows:
            s = staff.setdefault(r["staff_id"], {"staff_id": r["staff_id"], "name": names.get(r["staff_id"]),
                                                 "store_id": r["store_id"], "remakes": 0, "free_remakes": 0,
                                                 "alterations": 0, "free_alterations": 0})
            if r["kind"] == "remake":
                s["remakes"] += 1
                s["free_remakes"] += not r["charged"]
            else:
                s["alterations"] += 1
                s["free_alterations"] += not r["charged"]
        out = sorted((s for s in staff.values() if s["remakes"]), key=lambda s: (-s["free_remakes"], s["staff_id"]))
        return {"as_of": as_of, "from_exclusive": since, "staff": out[:int_arg(args, "limit", 20, 1, 60)]}
    return build_tool(
        "remakes_by_staff", "Remakes in the last `days` (default 30) per staff member: count, free (not charged) count, "
        "with alteration counts for comparison. Optional store_id.",
        {"days": {"type": "integer"}, "store_id": {"type": "string"}, "limit": {"type": "integer"}}, handler,
        area_ok=_area_ok(data_conn), area_label="the retail client's area")


def store_pos_tools(data_conn):
    return [make_refunds_by_staff(data_conn), make_discounts_by_staff(data_conn), make_remakes_by_staff(data_conn)]
