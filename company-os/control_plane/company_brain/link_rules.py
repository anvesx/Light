"""Link rules: code decides how new items connect to older ones. The model only sees pairs the rules mark unsure."""
import re

STOP = frozenset("a an the and or but so of to in on at for by with from is are was were be been it its this that these those i we you "
                 "they he she our your their us them me my as not no yes okay ok fine do does did will would can could should have has had "
                 "there then than too also just now very more some any "
                 "sorry well first said call cut really actually please thanks hello hi".split())
NUMBER_WORDS = ("one two three four five six seven eight nine ten eleven twelve").split()
MONTHS = ("january february march april may june july august september october november december "
          "jan feb mar apr jun jul aug sep sept oct nov dec").split()
CHOICE_WORDS = frozenset("whatsapp sms email gst hsn simple paid free all first".split())
QUANTITY = re.compile(r"\b\d{1,2}\s+(?:%s)\b|\b(?:%s)\b|\b\d+(?:\.\d+)?\b|\b(?:%s)\b" % (
    "|".join(MONTHS), "|".join(MONTHS), "|".join(NUMBER_WORDS)), re.I)
SAME_MIN_SHARED, SAME_MIN_JACCARD, SAME_MIN_OVERLAP = 3, 0.35, 0.7
ANSWER_WINDOW = 3  # lines after the question
ANSWER_RANK = {"decision": 0, "requirement": 1, "fact": 2}


def tokens(text):
    """Content words of a text: lower case, no stop words, plural s removed."""
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words if w not in STOP and len(w) > 1}


def quantities(text):
    """Dates, numbers and number words in a text."""
    return {" ".join(m.group(0).lower().split()) for m in QUANTITY.finditer(text or "")}


def choices(text):
    """Choice words (a channel, a format, a scope word) in a text."""
    return {w for w in re.findall(r"[a-z]+", (text or "").lower()) if w in CHOICE_WORDS}


def values_of(item, with_choices):
    found = quantities(item["text"])
    return found | choices(item["text"]) if with_choices else found


def conflicting(a, b, with_choices, strict=False):
    """Both items carry a value and the values differ. Strict: neither value set contains the other."""
    va, vb = values_of(a, with_choices), values_of(b, with_choices)
    if not va or not vb or va == vb:
        return False
    return not (va <= vb or vb <= va) if strict else True


def similarity(a, b):
    ta, tb = tokens(a["text"]), tokens(b["text"])
    shared = ta & tb
    union = ta | tb
    return len(shared), (len(shared) / len(union) if union else 0.0), (len(shared) / min(len(ta), len(tb)) if ta and tb else 0.0)


def order_key(item):
    """Time order of an item: when it was said, then when it was stored, then its id. Same rule as the store."""
    return (item["when"] or "")[:16], item["item_id"]


def compatible(a, b):
    """Items of different projects or deals never link."""
    for field in ("project_id", "deal_id"):
        if a.get(field) and b.get(field) and a[field] != b[field]:
            return False
    return True


def _pair_rule(newer, older):
    """The link of one pair as (rel, ...) or None, or "unsure"."""
    same_source = newer["source_id"] == older["source_id"]
    if newer["kind"] == "decision" and older["kind"] == "decision" and conflicting(newer, older, True):
        return "supersedes"
    if not same_source and newer["kind"] == older["kind"] and newer["kind"] in ("fact", "money") and conflicting(newer, older, False, True):
        return "contradicts"
    if not same_source and newer["kind"] == "requirement" and older["kind"] == "decision" and conflicting(newer, older, True):
        return "contradicts"
    shared, jaccard, overlap = similarity(newer, older)
    if newer["kind"] == older["kind"] and shared >= SAME_MIN_SHARED and (jaccard >= SAME_MIN_JACCARD or overlap >= SAME_MIN_OVERLAP):
        return "same_as"
    if newer["kind"] == older["kind"] == "requirement" and not same_source and shared >= SAME_MIN_SHARED:
        return "refines"
    if newer["kind"] == older["kind"] and shared == 2:
        return "unsure"
    return None


def plan_links(new_items, others, existing):
    """Decide links for the new items against the area's other live items.

    `existing` is a set of (from, rel, to). Returns {"links": [{"from","rel","to"}], "unsure": [{"a","b"}]}.
    """
    links, unsure, seen = [], [], set()
    answered = {to for (_, rel, to) in existing if rel == "answers"}
    live = {i["item_id"]: i for i in new_items + others}
    pool = list(live.values())
    for n in new_items:
        for o in pool:
            if o["item_id"] == n["item_id"] or o["topic"] is None or o["topic"] != n["topic"] or not compatible(n, o):
                continue
            pair = frozenset((n["item_id"], o["item_id"]))
            if pair in seen:
                continue
            seen.add(pair)
            newer, older = (n, o) if order_key(n) >= order_key(o) else (o, n)
            rel = _pair_rule(newer, older)
            if rel == "unsure":
                unsure.append({"a": newer["item_id"], "b": older["item_id"]})
            elif rel and (newer["item_id"], rel, older["item_id"]) not in existing:
                links.append({"from": newer["item_id"], "rel": rel, "to": older["item_id"]})
    links = _keep_latest_target(links, live)
    links += _answers(pool, answered, {(l["from"], l["rel"], l["to"]) for l in links} | existing, new_items)
    links += _follow_ups(pool, new_items, existing)
    return {"links": links, "unsure": unsure}


def _keep_latest_target(links, live):
    """A decision supersedes only the newest older decision; a duplicate points at one canonical item."""
    best = {}
    for l in links:
        if l["rel"] in ("supersedes", "same_as", "refines"):
            key = (l["from"], l["rel"])
            if key not in best or order_key(live[l["to"]]) > order_key(live[best[key]["to"]]):
                best[key] = l
    return [l for l in links if l["rel"] not in ("supersedes", "same_as", "refines") or best[(l["from"], l["rel"])] is l]


def _answers(pool, answered, existing, new_items):
    """A question is answered by the closest decision, requirement or fact a few lines later in the same source."""
    out, ids = [], {n["item_id"] for n in new_items}
    for q in sorted(pool, key=order_key):
        if q["kind"] != "question" or q["item_id"] in answered:
            continue
        options = [a for a in pool if a["source_id"] == q["source_id"] and a["topic"] == q["topic"] and a["kind"] in ANSWER_RANK
                   and 0 < a["line_from"] - q["line_to"] <= ANSWER_WINDOW and (a["item_id"] in ids or q["item_id"] in ids)
                   and (a["item_id"], "answers", q["item_id"]) not in existing]
        if options:
            best = min(options, key=lambda a: (ANSWER_RANK[a["kind"]], a["line_from"]))
            out.append({"from": best["item_id"], "rel": "answers", "to": q["item_id"]})
    return out


def _follow_ups(pool, new_items, existing):
    """A blocker follows up the newest older decision on its topic."""
    out = []
    for b in new_items:
        if b["kind"] != "blocker" or b["topic"] is None:
            continue
        before = [d for d in pool if d["kind"] == "decision" and d["topic"] == b["topic"] and compatible(b, d)
                  and order_key(d) < order_key(b)]
        if before:
            d = max(before, key=order_key)
            if (b["item_id"], "follows_up", d["item_id"]) not in existing:
                out.append({"from": b["item_id"], "rel": "follows_up", "to": d["item_id"]})
    return out


def scope_for(source, item, projects, deals):
    """Project and deal for an item from the source, a project name in the text, or the only one in the area."""
    project = item.get("project_id") or source.get("project_id")
    if not project:
        text = ((source.get("title") or "") + " " + item["text"]).lower()
        named = [p["project_id"] for p in projects if p["name"].lower() in text]
        project = named[0] if len(named) == 1 else (projects[0]["project_id"] if len(projects) == 1 else None)
    deal = item.get("deal_id") or source.get("deal_id") or (deals[0]["deal_id"] if len(deals) == 1 else None)
    return project, deal
