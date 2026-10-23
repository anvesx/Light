"""Hours and task counts per project as of a date. Shared by the project and staffing tools."""

OPEN_AS_OF = "(k.done_on IS NULL OR k.done_on > :as_of)"


def project_stats(conn, as_of, area_id=None, project_id=None):
    """One dict per project that has started by as_of."""
    sql = "SELECT * FROM projects WHERE start_on <= ?"
    params = [as_of]
    for column, value in (("client_id", area_id), ("project_id", project_id)):
        if value is not None:
            sql += f" AND {column} = ?"
            params.append(value)
    return [_one(conn, p, as_of) for p in conn.execute(sql + " ORDER BY project_id", params).fetchall()]


def _one(conn, p, as_of):
    pid, sow_id = p["project_id"], p["sow_id"]
    sow = conn.execute("SELECT estimate_hours, signed_on FROM sows WHERE sow_id = ?", (sow_id,)).fetchone()
    estimate = sow["estimate_hours"] if sow and sow["signed_on"] and sow["signed_on"] <= as_of else None
    changes = conn.execute(
        "SELECT accepted, SUM(hours_delta) AS h FROM sow_changes WHERE sow_id = ? AND date <= ? GROUP BY accepted",
        (sow_id, as_of)).fetchall()
    accepted = sum(c["h"] for c in changes if c["accepted"])
    unaccepted = sum(c["h"] for c in changes if not c["accepted"])
    logged = conn.execute(
        "SELECT COALESCE(SUM(l.hours), 0) FROM time_logs l JOIN tasks k ON k.task_id = l.task_id "
        "WHERE k.project_id = ? AND l.date <= ?", (pid, as_of)).fetchone()[0]
    t = conn.execute(
        f"SELECT COUNT(*) AS total, SUM({OPEN_AS_OF.replace(':as_of', '?')}) AS open_n, "
        f"SUM({OPEN_AS_OF.replace(':as_of', '?')} AND k.due_on < ?) AS overdue FROM tasks k WHERE k.project_id = ?",
        (as_of, as_of, as_of, pid)).fetchone()
    total_est = None if estimate is None else estimate + accepted
    open_n = t["open_n"] or 0
    return {
        "project_id": pid, "client_id": p["client_id"], "name": p["name"], "status": p["status"],
        "lead_id": p["lead_id"], "csm_id": p["csm_id"], "start_on": p["start_on"], "planned_end_on": p["planned_end_on"],
        "sow_id": sow_id, "sow_estimate_hours": estimate, "accepted_change_hours": accepted,
        "unaccepted_change_hours": unaccepted, "estimate_hours_with_changes": total_est,
        "hours_logged": round(logged, 1),
        "logged_pct_of_estimate": round(100 * logged / total_est, 1) if total_est else None,
        "tasks_total": t["total"], "tasks_open": open_n, "tasks_overdue": t["overdue"] or 0,
        "open_task_share": round(open_n / t["total"], 3) if t["total"] else None,
    }
