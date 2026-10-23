"""Entry points for the console and tests: ask for a trip, list requests, choose options, book after approval."""
from lifecycle_kit.approved_actions import execute_approved

from . import booking_store
from .request_parser import RequestError, normalize_request, parse_request

AGENT, AREA = "travel_booking", "devx-internal"
ADMIN_ROLES = frozenset({"ceo", "rnd_lead", "finance_lead"})   # console "admin" (contract C7)


def _conn(cos):
    return cos.memory.conn


def _is_admin(cos, person_id) -> bool:
    return cos.directory.role(person_id) in ADMIN_ROLES


def _result(row, run_id, status, letter, ok):
    return {"ok": ok, "request_id": row, "run_id": run_id, "status": status, "flights": [], "hotels": [], "round_trips": [],
            "out_of_policy": [], "approval_id": None, "letter": letter}


def request_trip(cos, caller_id, request) -> dict:
    """Search, rank and hold one trip request. Nothing is booked until an Admin approves the held approval."""
    conn = _conn(cos)
    booking_store.ensure_schema(conn)
    try:
        clean = parse_request(request) if isinstance(request, str) else normalize_request(request)
    except RequestError as e:
        rid = booking_store.new_request(conn, caller_id, {"raw": str(request)[:500]}, cos.clock.now)
        booking_store.update_request(conn, rid, status="refused", letter=str(e))
        return _result(rid, None, "refused", str(e), False)
    rid = booking_store.new_request(conn, caller_id, clean, cos.clock.now)
    run = cos.run(AGENT, caller_id, AREA, inputs={"request": clean, "request_id": rid})
    row = booking_store.get_request(conn, rid)
    if run.status == "held" and row["approval_id"]:
        return {**_result(rid, run.run_id, "held", row["letter"], True), "flights": row["flights"], "hotels": row["hotels"],
                "round_trips": row["round_trips"], "out_of_policy": row["out_of_policy"], "approval_id": row["approval_id"]}
    if run.status == "refused":
        status, letter = "refused", run.reason or "The request was refused."
    else:
        status = "failed"
        letter = run.reason or "No flight or hotel fits the travel policy for that request. Try another day."
    booking_store.update_request(conn, rid, status=status, run_id=run.run_id, letter=letter)
    return _result(rid, run.run_id, status, letter, False)


def _view(cos, row) -> dict:
    """One request for the console. The status follows the approval: held, booked, denied."""
    status = row["status"]
    if row["approval_id"] and status == "held":
        approval = cos.approvals.get(row["approval_id"])
        if approval and approval["status"] == "rejected":
            status = "denied"
    return {"request_id": row["request_id"], "requester_id": row["requester_id"], "status": status,
            "request": row["request"], "flights": row["flights"], "hotels": row["hotels"],
            "round_trips": row["round_trips"],
            "out_of_policy": row["out_of_policy"], "approval_id": row["approval_id"], "run_id": row["run_id"],
            "booking_ref": row["booking"]["booking_ref"] if row["booking"] else None,
            "total_inr": row["booking"]["total_inr"] if row["booking"] else None,
            "letter": row["letter"], "created_at": row["created_at"]}


def requests_for(cos, viewer_id, *, all_requests=False) -> list[dict]:
    """The viewer's own requests. Only an Admin may ask for all of them."""
    everyone = all_requests and _is_admin(cos, viewer_id)
    rows = booking_store.list_requests(_conn(cos), None if everyone else viewer_id)
    return [_view(cos, r) for r in rows]


def _refuse(reason):
    return {"ok": False, "reason": reason}


def choose_options(cos, request_id, flight_option_id, hotel_option_id, by_person_id) -> dict:
    """Swap the held approval for a new one with the chosen options. The old approval is rejected."""
    conn = _conn(cos)
    row = booking_store.get_request(conn, request_id)
    if row is None:
        return _refuse("unknown request")
    if by_person_id != row["requester_id"] and not _is_admin(cos, by_person_id):
        return _refuse("only the person who asked, or an Admin, may choose the options")
    old = cos.approvals.get(row["approval_id"]) if row["approval_id"] else None
    if row["booking"] or old is None or old["status"] != "pending":
        return _refuse("this request is not waiting for approval")
    flight = next((f for f in (row["round_trips"] or row["flights"]) if f["option_id"] == flight_option_id), None)
    hotel = next((h for h in row["hotels"] if h["option_id"] == hotel_option_id), None) if hotel_option_id else None
    if flight is None:
        return _refuse("that flight is not one of the options shown")
    if row["hotels"] and hotel is None:
        return _refuse("choose one of the hotels shown")
    if not row["hotels"] and hotel_option_id:
        return _refuse("this request has no hotel")
    total = flight["total_inr"] + (hotel["total_inr"] if hotel else 0)
    args = {"request_id": request_id, "flight_option_id": flight["option_id"],
            "hotel_option_id": hotel["option_id"] if hotel else "", "total_inr": total}
    cos.approvals.decide(old["approval_id"], False, by_person_id)
    new_id = cos.approvals.request(row["run_id"], AGENT, "book_travel", args, "book_travel is a risky action and needs a person's approval")
    booking_store.update_request(conn, request_id, approval_id=new_id)
    cos.memory.log_step(row["run_id"], "approval_replaced", {"old": old["approval_id"], "new": new_id, "by": by_person_id})
    return {"ok": True, "request_id": request_id, "approval_id": new_id, "status": "held", "flight": flight,
            "hotel": hotel, "total_inr": total}


def booking_after_approval(cos, approval_id) -> dict:
    """Book once, after an Admin approved. Rejected, pending, repeated or wrong-role approvals are skipped."""
    row = cos.approvals.get(approval_id)
    if row is None or row["agent"] != AGENT or row["tool"] != "book_travel":
        return {"status": "skipped", "reason": "not a travel booking approval"}
    if row["status"] == "approved" and not cos.policy.may_approve(cos.directory.role(row["decided_by"]), AGENT):
        return {"status": "skipped", "reason": "the approver's role may not approve travel"}
    out = execute_approved(approval_id, cos.approvals, cos.runtime.registry, cos.memory)
    if out["status"] == "ran" and out["result"].startswith("booked "):
        return {"status": "booked", "booking_ref": out["result"].split(" ", 1)[1], "approval_id": approval_id}
    return {"status": "failed" if out["status"] == "failed" else "skipped", "reason": out.get("reason") or out.get("result", "")}
