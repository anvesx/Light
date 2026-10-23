"""Finds the memory area of a calendar event, for the request trigger."""
from .people_directory import INTERNAL_AREA


def event_area(data_conn):
    def lookup(event_id):
        row = data_conn.execute("SELECT client_id FROM calendar_events WHERE event_id = ?", (event_id,)).fetchone()
        if row is None:
            return None
        return row["client_id"] or INTERNAL_AREA
    return lookup
