"""Role-based views of the project progress feed in central memory (the latest snapshot per project)."""
import json

from company_data.simulated_today import TODAY

FULL_ROLES = ("ceo", "rnd_lead")
OWN_ROLES = ("csm", "project_lead")
STATUSES = ("on track", "at risk", "behind")


def latest_snapshots(memory, as_of):
    """Newest progress snapshot per project made on or before as_of."""
    latest = {}
    for item in memory.items(kinds=["progress_snapshot"]):
        if item["created_at"][:10] > as_of:
            continue
        try:
            snap = json.loads(item["text"])
        except ValueError:
            continue
        latest[snap["project_id"]] = snap
    return latest


def _line(snap, client_names):
    return {"client_id": snap["client_id"], "client_name": client_names.get(snap["client_id"]),
            "project_id": snap["project_id"], "project_name": snap["project_name"], "status": snap["status"]}


def _team_totals(snaps):
    totals = {s: 0 for s in STATUSES}
    scope = {"not started": 0, "in progress": 0, "done": 0, "at risk": 0, "total": 0}
    for snap in snaps:
        totals[snap["status"]] += 1
        for k in scope:
            scope[k] += snap["scope_counts"].get(k, 0)
    return {"projects": len(snaps), "by_status": totals, "scope_items": scope,
            "open_flags": sum(len(s["flags"]) for s in snaps)}


def progress_for(person_id, memory, directory, data_conn, as_of=None) -> dict:
    """What this person may see of project progress. The shape depends on their role."""
    as_of = as_of or TODAY
    role = directory.role(person_id)
    snaps = latest_snapshots(memory, as_of)
    names = {r["client_id"]: r["name"] for r in data_conn.execute("SELECT client_id, name FROM clients")}
    out = {"as_of": as_of, "role": role}
    if role in FULL_ROLES:
        return {**out, "view": "full", "projects": [snaps[k] for k in sorted(snaps)]}
    if role == "hr":
        return {**out, "view": "team_totals", "totals": _team_totals(list(snaps.values()))}
    if role == "growth":
        return {**out, "view": "status_lines", "projects": [_line(snaps[k], names) for k in sorted(snaps)]}
    allowed = directory.client_access(person_id)
    visible = [snaps[k] for k in sorted(snaps) if snaps[k]["client_id"] in allowed]
    if role in OWN_ROLES:
        own = [s for s in visible if person_id in (s["csm_id"], s["lead_id"])]
        rest = [s for s in visible if s not in own]
        return {**out, "view": "own_detail", "projects": own, "other_projects": [_line(s, names) for s in rest]}
    return {**out, "view": "status_lines", "projects": [_line(s, names) for s in visible]}
