"""Request trigger: turns a person's message such as "prep me for EV07" into a task."""
import re

from contract.types import Task

PREP = re.compile(r"\bprep(?:are)?\b(?:\s+me)?(?:\s+for)?\s+(EV\w+)", re.IGNORECASE)
UNRESOLVED_AREA = "hold"  # no lookup or unknown event: the run can only read the hold area


def parse_request(text, caller_id, event_area=None):
    """Return a meeting_prep Task, or None. `event_area(event_id) -> area_id or None` finds the client."""
    match = PREP.search(text)
    if not match:
        return None
    event_id = match.group(1).upper()
    area_id = (event_area(event_id) if event_area else None) or UNRESOLVED_AREA
    return Task(agent="meeting_prep", caller_id=caller_id, area_id=area_id, trigger_kind="request",
                prompt=text, inputs={"event_id": event_id})
