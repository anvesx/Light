"""Adds the brain-era records: prospects, lost deals, their contacts and calls, monthly client invoices, two upcoming events."""
import json
import random
from datetime import date, timedelta

from company_data import company_roster as R
from company_data.simulated_today import TODAY

# lead id -> (client, stage, created, value INR, lost reason, call dates, call summaries)
NEW_LEADS = [
    ("L20", "C07", "negotiation", "2026-08-24", 4200000, None, ["2026-08-31", "2026-09-22"],
     ["Intro call with Meenal. CareNest runs 12 clinics and wants one booking app. They asked about timeline and budget.",
      "Follow-up with Meenal and Sameer. They compared us with one other vendor and asked for a paid pilot."]),
    ("L21", "C08", "proposal", "2026-09-08", 1800000, None, ["2026-09-15", "2026-10-06"],
     ["Intro call with Farida. Zaika runs 9 outlets and wants one billing system. They asked about offline billing.",
      "Second call with Farida and Dev. They want to see a plan for two outlets first."]),
    ("L22", "C09", "lost", "2026-07-06", 3600000, "Data storage question not answered; price too high",
     ["2026-07-13", "2026-08-03"],
     ["Intro call with Kunal. Swasth Labs wants a lab results portal for patients. They asked where data is stored.",
      "Proposal call with Kunal and Tanya. The data storage question stayed open and they found the price high."]),
    ("L23", "C10", "lost", "2026-06-15", 2400000, "Plan too long; wanted a phased MVP",
     ["2026-06-22", "2026-07-20"],
     ["Intro call with Vivek. KiranaKart wants an app for neighbourhood grocery shops.",
      "Proposal call with Vivek and Sheetal. The plan ran 9 months and they wanted a smaller first release."]),
]
UPCOMING = [  # title, start, attendees, client, project
    ("Client sync: Patient Booking App", "2026-10-20T08:30", ["P09", "P05", "X07", "X08"], "C04", "PR05"),
    ("Negotiation call: CareNest Clinics", "2026-10-19T16:30", ["P03", "X13", "X14"], "C07", None),
]


def D(s):
    return date.fromisoformat(s)


def email(name, dom):
    return name.lower().replace(" ", ".").replace("'", "") + "@" + dom


def add_brain_records(b, seed):
    rng = random.Random(seed + 17)
    for cid, name, industry, csm, am, status in R.NEW_CLIENTS:
        b.add("clients", client_id=cid, name=name, industry=industry, csm_id=csm, account_manager_id=am, status=status)
    names = {c[0]: c[1] for c in R.NEW_CLIENTS}
    for pid, name, cid in R.NEW_CLIENT_CONTACTS:
        b.add("people", person_id=pid, name=name, email=email(name, names[cid].lower().replace(" ", "-") + ".example"),
              role="client_contact", team="client", is_devx=0, client_id=cid, monthly_salary_inr=None, manager_id=None)
    contacts = {}
    for pid, _, cid in R.NEW_CLIENT_CONTACTS:
        contacts.setdefault(cid, []).append(pid)
    owner = {c[0]: c[4] for c in R.NEW_CLIENTS}
    for lead, cid, stage, created, value, reason, dates, summaries in NEW_LEADS:
        b.add("leads", lead_id=lead, client_id=cid, source=rng.choice(["referral", "event", "website", "outbound"]),
              owner_id=owner[cid], stage=stage, created_on=created, won_on=None, value_inr=value, lost_reason=reason)
        for d, text in zip(dates, summaries):
            b.add("growth_calls", call_id=b.nid("GC", 2), lead_id=lead, client_id=cid, date=d, owner_id=owner[cid],
                  attendees=json.dumps([owner[cid]] + contacts[cid][: 1 if d == dates[0] else 2]), summary=text)
    _add_client_invoices(b, rng)
    for title, start, att, cid, pid in UPCOMING:
        assert TODAY + "T09:00" < start <= (D(TODAY) + timedelta(days=1)).isoformat() + "T09:00", start  # next 24 hours
        b.add("calendar_events", event_id=b.nid("EV", 2), title=title, start_at=start, attendees=json.dumps(att),
              client_id=cid, project_id=pid, meeting_id=None)


def _months(first, last):
    y, m = int(first[:4]), int(first[5:7])
    while f"{y}-{m:02d}" <= last:
        yield f"{y}-{m:02d}"
        m += 1
        if m > 12:
            y, m = y + 1, 1


def _add_client_invoices(b, rng):
    """One invoice per month per won project, from its start month to Oct 2026 (or the month it ended)."""
    leads = {l["lead_id"]: l for l in b.rows["leads"]}
    for p in b.rows["projects"]:
        lead = leads[f"L{int(p['project_id'][2:]):02d}"]
        end = min(p["planned_end_on"][:7], TODAY[:7])
        if p["status"] == "paused":
            end = "2026-08"
        months = list(_months(p["start_on"][:7], end))
        planned = len(list(_months(p["start_on"][:7], p["planned_end_on"][:7])))
        base = round(lead["value_inr"] / planned / 1000) * 1000
        for i, month in enumerate(months):
            late = month == TODAY[:7]
            status = "sent" if late else "overdue" if (month == "2026-09" and rng.random() < 0.3) else "paid"
            b.add("client_invoices", invoice_id=b.nid("CI", 3), client_id=p["client_id"], project_id=p["project_id"],
                  month=month, amount_inr=base, status=status)
