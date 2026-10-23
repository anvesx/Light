"""Reads and writes the travel_requests and travel_bookings tables (on the company memory connection)."""
import json
from hashlib import sha1
from pathlib import Path

JSON_COLUMNS = {"request_json": "request", "flights_json": "flights", "hotels_json": "hotels",
                "out_of_policy_json": "out_of_policy", "round_trips_json": "round_trips"}
UPDATABLE = {"status", "run_id", "approval_id", "flights_json", "hotels_json", "out_of_policy_json", "round_trips_json", "letter"}


def ensure_schema(conn):
    conn.executescript(Path(__file__).with_name("schema.sql").read_text())
    if "round_trips_json" not in {r[1] for r in conn.execute("PRAGMA table_info(travel_requests)")}:   # older database
        conn.execute("ALTER TABLE travel_requests ADD COLUMN round_trips_json TEXT NOT NULL DEFAULT '[]'")


def new_request(conn, requester_id, request, now) -> str:
    n = conn.execute("SELECT COUNT(*) FROM travel_requests").fetchone()[0] + 1
    request_id = f"TRQ{n:04d}"
    with conn:
        conn.execute("INSERT INTO travel_requests (request_id, requester_id, request_json, created_at) VALUES (?, ?, ?, ?)",
                     (request_id, requester_id, json.dumps(request, sort_keys=True), now))
    return request_id


def update_request(conn, request_id, **fields):
    """Fields are column names; dict and list values are stored as JSON."""
    bad = set(fields) - UPDATABLE
    if bad:
        raise ValueError(f"cannot update {sorted(bad)}")
    values = [v if isinstance(v, (str, type(None))) else json.dumps(v, sort_keys=True) for v in fields.values()]
    with conn:
        conn.execute(f"UPDATE travel_requests SET {', '.join(f'{k} = ?' for k in fields)} WHERE request_id = ?",
                     (*values, request_id))


def _row(conn, row):
    out = {k: v for k, v in dict(row).items() if k not in JSON_COLUMNS}
    for column, name in JSON_COLUMNS.items():
        out[name] = json.loads(row[column])
    booking = conn.execute("SELECT * FROM travel_bookings WHERE request_id = ?", (row["request_id"],)).fetchone()
    out["booking"] = dict(booking) if booking else None
    return out


def get_request(conn, request_id):
    row = conn.execute("SELECT * FROM travel_requests WHERE request_id = ?", (request_id,)).fetchone()
    return _row(conn, row) if row else None


def list_requests(conn, requester_id=None):
    sql, params = "SELECT * FROM travel_requests", ()
    if requester_id is not None:
        sql, params = sql + " WHERE requester_id = ?", (requester_id,)
    return [_row(conn, r) for r in conn.execute(sql + " ORDER BY request_id DESC", params)]


def booking_ref_for(request_id, flight_option_id, hotel_option_id) -> str:
    return "SIM-" + sha1(f"{request_id}|{flight_option_id}|{hotel_option_id}".encode()).hexdigest()[:8].upper()


def add_booking(conn, request_id, flight_option_id, hotel_option_id, pax, total_inr, now) -> str:
    """Write the booking and mark the request booked. A second booking for one request is refused."""
    ref = booking_ref_for(request_id, flight_option_id, hotel_option_id)
    with conn:
        conn.execute("INSERT INTO travel_bookings VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (ref, request_id, flight_option_id, hotel_option_id, pax, total_inr, now))
        conn.execute("UPDATE travel_requests SET status = 'booked' WHERE request_id = ?", (request_id,))
    return ref
