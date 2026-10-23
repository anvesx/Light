"""Source readers: turn a Fathom JSON, Word file, email, chat export or plain text into (meta, lines)."""
import email
import io
import json
import re
import zipfile
from email import policy
from email.utils import getaddresses, parsedate_to_datetime
from xml.etree import ElementTree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CHAT_LINE = re.compile(r"^\[(\d\d)/(\d\d)/(\d\d), (\d\d:\d\d)\] ([^:]+): (.*)$")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
MAX_PART = 5_000_000


def _lines(rows):
    return [{**row, "line_no": n} for n, row in enumerate(rows, start=1)]


def _person(name, address=""):
    return {"name": (name or "").strip(), "email": (address or "").strip().lower()}


def read_fathom_json(text):
    data = json.loads(text)
    rows = []
    for seg in data.get("transcript", []):
        speaker = seg.get("speaker") or {}
        h, m, s = (int(x) for x in (seg.get("timestamp") or "00:00:00").split(":"))
        rows.append({"speaker": speaker.get("display_name") or "", "text": seg.get("text", ""), "t_sec": h * 3600 + m * 60 + s})
    people = {}
    for p in data.get("calendar_invitees", []):
        people[p.get("email", "").lower() or p.get("name", "")] = _person(p.get("name"), p.get("email"))
    for seg in data.get("transcript", []):
        sp = seg.get("speaker") or {}
        if sp.get("matched_calendar_invitee_email"):
            people.setdefault(sp["matched_calendar_invitee_email"].lower(), _person(sp.get("display_name"), sp["matched_calendar_invitee_email"]))
    meta = {"title": data.get("title") or "", "occurred_at": (data.get("created_at") or "")[:16] or None,
            "participants": list(people.values()), "origin_ref": str(data["recording_id"]) if "recording_id" in data else None}
    return meta, _lines(rows)


def _docx_part(archive, name):
    info = archive.getinfo(name)
    if info.file_size > MAX_PART:
        raise ValueError(f"{name} is too large")
    return ElementTree.fromstring(archive.read(name))


def read_docx(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        body = _docx_part(archive, "word/document.xml")
        core = _docx_part(archive, "docProps/core.xml") if "docProps/core.xml" in archive.namelist() else None
    paragraphs = ["".join(t.text or "" for t in p.iter(f"{W}t")).strip() for p in body.iter(f"{W}p")]
    rows = [{"speaker": "", "text": p} for p in paragraphs if p]
    title, created = "", None
    if core is not None:
        for el in core:
            tag = el.tag.rsplit("}", 1)[-1]
            if tag == "title":
                title = (el.text or "").strip()
            elif tag == "created" and el.text:
                created = el.text.strip()[:16]
    if not title and rows:
        title = rows[0]["text"][:80]
    addresses = sorted({a.lower() for r in rows[:10] for a in EMAIL.findall(r["text"])})
    return {"title": title, "occurred_at": created, "participants": [_person("", a) for a in addresses],
            "origin_ref": None}, _lines(rows)


def read_eml(data):
    msg = email.message_from_bytes(data, policy=policy.default)
    body = msg.get_body(preferencelist=("plain",))
    text = body.get_content() if body is not None else ""
    sender = getaddresses([str(msg.get("From", ""))])
    name = sender[0][0] if sender else ""
    rows = [{"speaker": name or (sender[0][1] if sender else ""), "text": ln.strip()} for ln in text.splitlines() if ln.strip()]
    people = {}
    for header in ("From", "To", "Cc"):
        for n, a in getaddresses([str(msg.get(header, ""))]):
            if a:
                people.setdefault(a.lower(), _person(n, a))
    occurred = None
    try:
        occurred = parsedate_to_datetime(str(msg["Date"])).strftime("%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        pass
    return {"title": str(msg.get("Subject", "")), "occurred_at": occurred, "participants": list(people.values()),
            "origin_ref": str(msg["Message-ID"]).strip("<>") if msg.get("Message-ID") else None}, _lines(rows)


def read_chat(text):
    rows, names, first = [], [], None
    for raw in text.splitlines():
        m = CHAT_LINE.match(raw.strip())
        if m:
            dd, mm, yy, hhmm, name, body = m.groups()
            at = f"20{yy}-{mm}-{dd}T{hhmm}"
            first = first or at
            if name not in names:
                names.append(name)
            rows.append({"speaker": name, "text": body, "at": at})
        elif raw.strip() and rows:
            rows[-1]["text"] += " " + raw.strip()
    title = "Chat: " + ", ".join(names) if names else ""
    return {"title": title, "occurred_at": first, "participants": [_person(n) for n in names], "origin_ref": None}, _lines(rows)


def read_plain(text):
    rows = [{"speaker": "", "text": ln.strip()} for ln in text.splitlines() if ln.strip()]
    return {"title": rows[0]["text"][:80] if rows else "", "occurred_at": None, "participants": [], "origin_ref": None}, _lines(rows)
