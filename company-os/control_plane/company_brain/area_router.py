"""Area router: decide which client area a new source belongs to, or send it to hold."""
import re
import sqlite3
from collections import Counter

GENERIC_DOMAINS = frozenset({"gmail.com", "outlook.com", "yahoo.com", "hotmail.com", "icloud.com", "proton.me"})
DEVX_DOMAINS = frozenset({"devx-demo.example", "devxlabs.ai"})


def _clean(participants):
    out = []
    for p in participants or []:
        if isinstance(p, str):
            out.append({"name": p if "@" not in p else "", "email": p if "@" in p else ""})
        else:
            out.append({"name": p.get("name") or "", "email": p.get("email") or ""})
    return out


def _real_area(data_conn, area_id):
    if area_id == "devx-internal":
        return True
    return data_conn.execute("SELECT 1 FROM clients WHERE client_id = ?", (area_id,)).fetchone() is not None


def _contact_client(data_conn, person):
    """The client of a non-DevX person, found by email first and by exact name second."""
    if person["email"]:
        row = data_conn.execute("SELECT client_id FROM people WHERE lower(email) = ? AND client_id IS NOT NULL",
                                (person["email"].strip().lower(),)).fetchone()
        if row:
            return row["client_id"]
    if person["name"]:
        row = data_conn.execute("SELECT client_id FROM people WHERE lower(name) = ? AND client_id IS NOT NULL AND is_devx = 0",
                                (person["name"].strip().lower(),)).fetchone()
        if row:
            return row["client_id"]
    return None


def _domain(address):
    return address.rsplit("@", 1)[-1].strip().lower() if "@" in address else ""


def devx_domains(data_conn):
    rows = data_conn.execute("SELECT email FROM people WHERE is_devx = 1 AND email IS NOT NULL")
    return DEVX_DOMAINS | {_domain(r["email"]) for r in rows}


def _client_domains(data_conn):
    """Domain -> client id, for client contacts. A domain shared by two clients, or a public one, is left out."""
    skip, found = GENERIC_DOMAINS | devx_domains(data_conn), {}
    for r in data_conn.execute("SELECT email, client_id FROM people WHERE client_id IS NOT NULL AND email IS NOT NULL"):
        d = _domain(r["email"])
        if d and d not in skip:
            found.setdefault(d, set()).add(r["client_id"])
    return {d: next(iter(c)) for d, c in found.items() if len(c) == 1}


def _calendar_client(data_conn, title):
    try:
        rows = data_conn.execute("SELECT DISTINCT client_id FROM calendar_events WHERE lower(title) = ? AND client_id IS NOT NULL",
                                 ((title or "").strip().lower(),)).fetchall()
    except sqlite3.OperationalError:
        return None
    return rows[0]["client_id"] if len(rows) == 1 else None


def _project_in_title(data_conn, title):
    lowered = (title or "").lower()
    rows = [r for r in data_conn.execute("SELECT name, client_id FROM projects") if r["name"].lower() in lowered]
    return max(rows, key=lambda r: (len(r["name"]), r["client_id"]))["client_id"] if rows else None


def client_in_title(data_conn, title):
    """A client named in the title, by full name or by its first word (five letters or more, used by one client only)."""
    lowered = (title or "").lower()
    rows = [(r["client_id"], r["name"].lower()) for r in data_conn.execute("SELECT client_id, name FROM clients")]
    full = [(len(n), c) for c, n in rows if n in lowered]
    if full:
        return max(full)[1]
    brands = {}
    for c, n in rows:
        word = n.split()[0] if n.split() else ""
        if len(word) >= 5:
            brands.setdefault(word, set()).add(c)
    hits = {next(iter(c)) for w, c in brands.items() if len(c) == 1 and re.search(rf"\b{re.escape(w)}\b", lowered)}
    return next(iter(hits)) if len(hits) == 1 else None


def title_names_client(data_conn, title):
    """True when the title names a known client, prospect or one of their projects."""
    return bool(_project_in_title(data_conn, title) or client_in_title(data_conn, title))


def route(data_conn, participants, title, hint_area=None):
    """Return (area_id, reason). In order: hint, contact, domain, calendar_event, project_in_title, client_in_title, else hold."""
    if hint_area and _real_area(data_conn, hint_area):
        return hint_area, "hint"
    people = _clean(participants)
    clients = Counter(c for c in (_contact_client(data_conn, p) for p in people) if c)
    if clients:
        return sorted(clients.items(), key=lambda kv: (-kv[1], kv[0]))[0][0], "contact"
    domains = _client_domains(data_conn)
    by_domain = Counter(domains[d] for d in (_domain(p["email"]) for p in people) if d in domains)
    if by_domain:
        return sorted(by_domain.items(), key=lambda kv: (-kv[1], kv[0]))[0][0], "domain"
    for reason, client in (("calendar_event", _calendar_client(data_conn, title)),
                           ("project_in_title", _project_in_title(data_conn, title)),
                           ("client_in_title", client_in_title(data_conn, title))):
        if client:
            return client, reason
    return "hold", "no_match"
