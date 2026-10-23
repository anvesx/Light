"""Reads a trip request from words or a dict and checks it. The text is only read for cities, dates and numbers."""
import re
from datetime import date, timedelta

from company_data.generate_trips import HOTELS
from company_data.simulated_today import TODAY
from control_plane.connectors.fare_search import route_hours

PAX_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
ALIASES = {"bangalore": "Bengaluru", "bombay": "Mumbai"}
CITY_NAMES = {c.lower(): c for c in HOTELS} | ALIASES
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
CITY = "(" + "|".join(sorted(CITY_NAMES, key=len, reverse=True)) + ")"
MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
DATE_PATTERNS = (rf"(\d{{4}})-(\d{{2}})-(\d{{2}})", rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+{MONTH}(?:,?\s+(\d{{4}}))?",
                 rf"{MONTH}\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?")
RETURN_RE = re.compile(r"(?:back|return(?:ing|s)?|coming back)\s*(?:on|by)?\s*", re.I)
MAX_PAX, PURPOSE_LIMIT = 9, 80


class RequestError(ValueError):
    """A request that cannot be used. The message is plain words for the person."""


def _find_date(text):
    """First date in the text as (iso, start, end), or None. Month names without a year take the next such day."""
    best = None
    for n, pattern in enumerate(DATE_PATTERNS):
        m = re.search(pattern, text, re.I)
        if not m or (best and m.start() >= best[1]):
            continue
        g = m.groups()
        if n == 0:
            y, mo, d = int(g[0]), int(g[1]), int(g[2])
        else:
            d, mo, y = (int(g[0]), MONTHS[g[1].lower()[:3]], g[2]) if n == 1 else (int(g[1]), MONTHS[g[0].lower()[:3]], g[2])
            y = int(y) if y else int(TODAY[:4])
        try:
            iso = date(y, mo, d).isoformat()
        except ValueError:
            raise RequestError(f"{m.group(0)!r} is not a real date. Please write the date like 2026-10-28.")
        if n != 0 and not g[2] and iso < TODAY:
            iso = date(y + 1, mo, d).isoformat()
        best = (iso, m.start(), m.end())
    return best


def _pax(text):
    m = re.search(r"\b(\d+|" + "|".join(PAX_WORDS) + r")\s+(?:people|persons?|passengers|travellers|travelers|pax|of us|seats)\b", text, re.I) \
        or re.search(r"\bfor\s+(\d+|" + "|".join(PAX_WORDS) + r")\b(?!\s*(?:nights?|days?))", text, re.I)
    if not m:
        raise RequestError("Say how many people are travelling, for example 'for 3 people'.")
    word = m.group(1).lower()
    return int(word) if word.isdigit() else PAX_WORDS[word]


def parse_request(text: str) -> dict:
    """'flights for 3 people Mumbai to Pune on 2026-10-28, back on 2026-10-29' -> a request dict."""
    if not isinstance(text, str) or not text.strip():
        raise RequestError("The request is empty. Say who travels, where and when.")
    text = text[:500]
    route = re.search(rf"\b{CITY}\s+to\s+{CITY}\b", text, re.I)
    if not route:
        raise RequestError("I could not find the route. Write it like 'Mumbai to Pune'. Cities: " + ", ".join(sorted(HOTELS)) + ".")
    request = {"from_city": CITY_NAMES[route.group(1).lower()], "to_city": CITY_NAMES[route.group(2).lower()],
               "pax": _pax(text)}
    back = RETURN_RE.search(text)
    rest = text
    if back:
        found = _find_date(text[back.end():])
        if found:
            request["return_on"] = found[0]
            rest = text[:back.start()] + " " + text[back.end() + found[2]:]
    found = _find_date(rest)
    if not found:
        raise RequestError("I could not find the travel date. Write it like 'on 2026-10-28'.")
    request["depart_on"] = found[0]
    nights = re.search(r"\bfor\s+(\d{1,2})\s+nights?\b", text, re.I)
    if nights and "return_on" not in request:
        request["return_on"] = (date.fromisoformat(found[0]) + timedelta(days=int(nights.group(1)))).isoformat()
    client = re.search(r"\bC\d{2}\b", text)
    if client:
        request["client_id"] = client.group(0)
    purpose = re.search(r"purpose:\s*([^,.;\n]+)", text, re.I)
    request["purpose"] = purpose.group(1).strip() if purpose else "business trip"
    return normalize_request(request)


def normalize_request(request: dict) -> dict:
    """Check a request dict and return a clean copy. Raises RequestError in plain words."""
    if not isinstance(request, dict):
        raise RequestError("The request must be text or a dict.")
    city = lambda key: CITY_NAMES.get(str(request.get(key, "")).strip().lower())
    out = {"from_city": city("from_city"), "to_city": city("to_city")}
    if not out["from_city"] or not out["to_city"]:
        raise RequestError("I know these cities: " + ", ".join(sorted(HOTELS)) + ". Please pick two of them.")
    if out["from_city"] == out["to_city"]:
        raise RequestError("The two cities are the same.")
    if route_hours(out["from_city"], out["to_city"]) is None:
        raise RequestError(f"No flights run between {out['from_city']} and {out['to_city']}.")
    pax = request.get("pax")
    if isinstance(pax, bool) or not isinstance(pax, int) or not 1 <= pax <= MAX_PAX:
        raise RequestError(f"The number of people must be a whole number from 1 to {MAX_PAX}.")
    out["pax"] = pax
    for key in ("depart_on", "return_on"):
        value = request.get(key)
        if value is None and key == "return_on":
            continue
        try:
            out[key] = date.fromisoformat(str(value)).isoformat()
        except ValueError:
            raise RequestError(f"{key.replace('_', ' ')} must be a real date like 2026-10-28.")
    if out["depart_on"] < TODAY:
        raise RequestError(f"{out['depart_on']} is in the past. Today is {TODAY}.")
    if "return_on" in out and out["return_on"] < out["depart_on"]:
        raise RequestError("The return date is before the travel date.")
    client = request.get("client_id")
    if client is not None:
        if not isinstance(client, str) or not re.fullmatch(r"C\d{2}", client):
            raise RequestError("The client id must look like C07.")
        out["client_id"] = client
    purpose = re.sub(r"[^\w .,'&/-]", "", str(request.get("purpose") or "business trip"))[:PURPOSE_LIMIT].strip()
    out["purpose"] = purpose or "business trip"
    return out


def nights_of(request: dict) -> int:
    """Hotel nights: the days between the travel date and the return date. No return date means no hotel."""
    if not request.get("return_on"):
        return 0
    return (date.fromisoformat(request["return_on"]) - date.fromisoformat(request["depart_on"])).days
