"""Redaction for the playbook library: find and remove names, emails, phone numbers and salary words."""
import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"\+\d[\d\s-]{8,}\d|(?<![\d-])\d{5}[\s-]?\d{5}(?![\d-])")
SALARY = re.compile(r"\b(?:salary|salaries|ctc|stipend|payroll|appraisal)\b", re.I)
GREETING = re.compile(r"(?:\b(?:so|hi|hello|hey|thanks|thank you)\s+)?\[name\][\s,.!]*(?=[A-Za-z])", re.I)
LEADING_FILLER = re.compile(r"^(?:(?:yes|yeah|okay|ok|fine|great|sure|done|noted|right|so)\b[\s,.!-]*)+", re.I)


def _names(data_conn):
    """Return (client names, person names) as lower-case sets. First names count too."""
    clients, people = set(), set()
    if data_conn is None:
        return clients, people
    for r in data_conn.execute("SELECT name FROM clients"):
        clients.add(r["name"].lower())
        clients.add(r["name"].split()[0].lower())
    for r in data_conn.execute("SELECT name FROM people"):
        full = r["name"].lower()
        people.add(full)
        people.update(p for p in full.split() if len(p) >= 3)
    return clients, people


def _word(name):
    return re.compile(rf"(?<![\w]){re.escape(name)}(?![\w])", re.I)


def find_leaks(text, data_conn) -> list[str]:
    """Return what in the text must not reach the library: contact names, emails, phone numbers, salary words."""
    text = text or ""
    leaks = [m.group(0) for m in EMAIL.finditer(text)] + [m.group(0).strip() for m in PHONE.finditer(text)]
    leaks += [m.group(0) for m in SALARY.finditer(text)]
    clients, people = _names(data_conn)
    for n in sorted(clients | people, key=len, reverse=True):
        found = _word(n).search(text)
        if found:
            leaks.append(found.group(0))
    return leaks


def redact(text, data_conn) -> str:
    """Remove a leading greeting or name, then replace emails, phones, names and salary words."""
    text = LEADING_FILLER.sub("", (text or "").strip())
    clients, people = _names(data_conn)
    text = EMAIL.sub("[email]", text)
    text = PHONE.sub("[phone]", text)
    text = SALARY.sub("[pay]", text)
    for name in sorted(clients, key=len, reverse=True):
        text = _word(name).sub("the client", text)
    first = re.match(r"^(?:" + "|".join(re.escape(n) for n in sorted(people, key=len, reverse=True)) + r")\b[\s,.!-]*", text, re.I) \
        if people else None
    if first:
        text = text[first.end():]
        text = LEADING_FILLER.sub("", text)
    for name in sorted(people, key=len, reverse=True):
        text = _word(name).sub("[name]", text)
    text = re.sub(r"([.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), GREETING.sub("", text)).strip()
    return text[:1].upper() + text[1:]
