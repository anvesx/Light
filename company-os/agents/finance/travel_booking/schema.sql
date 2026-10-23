-- Travel booking tables, kept in company memory. Safe to run many times.
CREATE TABLE IF NOT EXISTS travel_requests (
    request_id TEXT PRIMARY KEY,
    requester_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'held', 'refused', 'failed', 'booked')),
    request_json TEXT NOT NULL,
    run_id TEXT,
    approval_id TEXT,
    flights_json TEXT NOT NULL DEFAULT '[]',
    hotels_json TEXT NOT NULL DEFAULT '[]',
    out_of_policy_json TEXT NOT NULL DEFAULT '[]',
    round_trips_json TEXT NOT NULL DEFAULT '[]',
    letter TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

-- One booking per request. The approval id is unique, so one approval can book only once.
CREATE TABLE IF NOT EXISTS travel_bookings (
    booking_ref TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE REFERENCES travel_requests(request_id),
    flight_option_id TEXT NOT NULL,
    hotel_option_id TEXT,
    pax INTEGER NOT NULL,
    total_inr INTEGER NOT NULL,
    booked_at TEXT NOT NULL
);
