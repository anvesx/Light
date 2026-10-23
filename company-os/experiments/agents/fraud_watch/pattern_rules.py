"""Pure rules that find unusual store patterns. Each staff member is compared with the rest of their store."""
import re

WINDOW_DAYS = 30
MIN_CASH_REFUNDS = 5       # the planted rule in the data: 5 or more in 30 days
MIN_SELF_APPROVED = 2      # a repeat; normal staff here have none, so one event alone is not a pattern
MIN_FREE_REMAKES = 5
PEER_RATIO = 3             # must be at least 3 times the store's normal per person

KIND_CASH = "many_cash_refunds"
KIND_SELF = "self_approved_discounts"
KIND_REMAKE = "repeated_free_remakes"

BANNED = re.compile(r"\b(fraud\w*|theft\w*|thie(?:f|ves)|steal\w*|stole\w*|stolen|cheat\w*)\b", re.I)


def _peer_average(rows, key, store_id, staff_id, store_staff):
    others = sum(r[key] for r in rows if r["store_id"] == store_id and r["staff_id"] != staff_id)
    return others / max(1, len(store_staff.get(store_id, ())) - 1)


def _store_staff(*results):
    seen = {}
    for res in results:
        for r in res.get("staff", []):
            seen.setdefault(r["store_id"], set()).add(r["staff_id"])
    return seen


def find_patterns(refunds, discounts, remakes):
    """Take the three tool results (dicts) and return a list of pattern dicts, sorted for a stable order."""
    staff_at = _store_staff(refunds, {"staff": discounts.get("staff", [])}, remakes)
    window = f"{refunds.get('from_exclusive')} to {refunds.get('as_of')}"
    out = []
    for r in refunds.get("staff", []):
        n = r["cash_refunds"]
        peer = _peer_average(refunds["staff"], "cash_refunds", r["store_id"], r["staff_id"], staff_at)
        if n >= MIN_CASH_REFUNDS and n >= PEER_RATIO * peer:
            out.append(_pattern(KIND_CASH, r, {"cash_refunds": n, "all_refunds": r["refunds"],
                                               "refund_total_inr": r["amount_inr"], "store_peer_average": round(peer, 1)},
                                f"{n} of {r['refunds']} refunds were paid in cash (refund total Rs {r['amount_inr']}); "
                                f"other staff at the store average {round(peer, 1)} cash refunds. Window: {window}."))
    for d in discounts.get("staff", []):
        n = d["self_approved"]
        peer = _peer_average(discounts["staff"], "self_approved", d["store_id"], d["staff_id"], staff_at)
        if n >= MIN_SELF_APPROVED and n >= PEER_RATIO * peer:
            out.append(_pattern(KIND_SELF, d, {"self_approved": n, "all_discounts": d["discounts"],
                                               "avg_pct": d["avg_pct"], "otp_retries": d["otp_retries_total"],
                                               "store_peer_average": round(peer, 1)},
                                f"{n} of {d['discounts']} discounts were approved by the same person who asked for them "
                                f"(average {d['avg_pct']} percent, {d['otp_retries_total']} OTP retries); other staff at the "
                                f"store average {round(peer, 1)} such discounts. Window: {window}."))
    for m in remakes.get("staff", []):
        n = m["free_remakes"]
        peer = _peer_average(remakes["staff"], "free_remakes", m["store_id"], m["staff_id"], staff_at)
        if n >= MIN_FREE_REMAKES and n >= PEER_RATIO * peer:
            out.append(_pattern(KIND_REMAKE, m, {"free_remakes": n, "all_remakes": m["remakes"],
                                                 "store_peer_average": round(peer, 1)},
                                f"{n} free remakes (not charged) out of {m['remakes']} remakes; other staff at the store "
                                f"average {round(peer, 1)} free remakes. Window: {window}."))
    return sorted(out, key=lambda p: (p["kind"], p["staff_id"]))


def _pattern(kind, row, facts, evidence):
    return {"kind": kind, "staff_id": row["staff_id"], "staff_name": row.get("name"), "store_id": row["store_id"],
            "facts": facts, "evidence": evidence}
