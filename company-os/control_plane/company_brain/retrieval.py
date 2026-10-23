"""Retrieval: rank past playbooks for a deal by industry group and tag overlap. No model, no embeddings."""
from control_plane.company_memory import AreaDenied

GROUPS = (frozenset({"healthcare", "diagnostics"}), frozenset({"retail", "restaurant chain", "grocery tech"}))


def _group(industry):
    industry = (industry or "").strip().lower()
    for group in GROUPS:
        if industry in group:
            return group
    return frozenset({industry}) if industry else frozenset()


def _deal_tags(scoped_brain, deal):
    if deal.get("tags"):
        return set(deal["tags"])
    try:
        items = scoped_brain.brain_items(deal["area_id"], deal_id=deal.get("deal_id"))
    except (AreaDenied, KeyError):
        return set()
    return {i["topic"] for i in items if i.get("topic")}


def similar_deals(scoped_brain, deal, k=3):
    """Top k playbooks for the deal: [{"playbook_id", "area_id", "score", "why", ...}], best first, ties by deal id."""
    tags = _deal_tags(scoped_brain, deal)
    group = _group(deal.get("industry"))
    ranked = []
    for pb in scoped_brain.playbooks():
        if pb["deal_id"] == deal.get("deal_id") or pb["area_id"] == deal.get("area_id"):
            continue
        same = bool(group) and pb["industry"] is not None and pb["industry"].strip().lower() in group
        shared = sorted(tags & set(pb["tags"]))
        union = tags | set(pb["tags"])
        score = 0.5 * same + 0.5 * (len(shared) / len(union) if union else 0.0)
        why = []
        if same:
            why.append(f"same industry group ({pb['industry']})")
        if shared:
            why.append("shared topics: " + ", ".join(shared))
        ranked.append(({"playbook_id": pb["playbook_id"], "area_id": pb["area_id"], "score": round(score, 4),
                        "why": "; ".join(why) or "no match", "deal_id": pb["deal_id"], "outcome": pb["outcome"]}))
    ranked.sort(key=lambda r: (-r["score"], r["deal_id"]))
    one_per_client = {}  # a client with two closed deals shows once, with its best playbook
    for r in ranked:
        one_per_client.setdefault(r["area_id"], r)
    return list(one_per_client.values())[:k]
