"""Time-aware views of memory: what was open or decided as of a date, so exams cannot see the future."""
from datetime import date, timedelta

CLOSING_LINKS = ("answers", "supersedes")


def _closed_before(scoped_memory, item_id, as_of):
    for link in scoped_memory.links_of(item_id):
        if link["to_id"] == item_id and link["rel"] in CLOSING_LINKS and link["created_at"] < as_of:
            return link
    return None


def open_items_as_of(scoped_memory, area_id, as_of, kinds=("question", "task")):
    """Items created before as_of with no answers or supersedes link made before as_of."""
    items = scoped_memory.items(area_id, kinds=list(kinds), before=as_of)
    return [i for i in items if _closed_before(scoped_memory, i["item_id"], as_of) is None]


def recent_decisions_as_of(scoped_memory, area_id, as_of, days=30, kinds=("decision",)):
    """Decisions made in the `days` before as_of that were not superseded before as_of."""
    since = (date.fromisoformat(as_of[:10]) - timedelta(days=days)).isoformat()
    out = []
    for item in scoped_memory.items(area_id, kinds=list(kinds), before=as_of):
        if item["created_at"] < since or _closed_before(scoped_memory, item["item_id"], as_of):
            continue
        answers = [l["to_id"] for l in scoped_memory.links_of(item["item_id"])
                   if l["from_id"] == item["item_id"] and l["rel"] == "answers"]
        out.append({**item, "answers": answers})
    return out
