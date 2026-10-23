"""Deterministic stand-in for the model: rewrites the code's patterns in neutral words."""
import json

from contract.types import ModelReply

from .pack import MARKER

WHY = {
    "many_cash_refunds": "Cash refunds leave no card trail, so a high share from one person is worth a second look.",
    "self_approved_discounts": "Discounts are meant to be approved by a second person; the same person on both sides skips that check.",
    "repeated_free_remakes": "Free remakes cost the store stock and labour, so a high count from one person is worth a look.",
}
NEXT = {
    "many_cash_refunds": "Review these refunds with the store manager and check the receipts and the customers' returns.",
    "self_approved_discounts": "Review these discounts with the store manager and check who held the approval code.",
    "repeated_free_remakes": "Review these remakes with the store manager and check the reasons recorded for each.",
}


def brain(request):
    prompt = request.messages[0]["content"]
    patterns, _ = json.JSONDecoder().raw_decode(prompt[prompt.index(MARKER) + len(MARKER):].lstrip())
    items = [{"kind": p["kind"], "staff_id": p["staff_id"], "store_id": p["store_id"], "evidence": p["evidence"],
              "why_it_matters": WHY[p["kind"]], "next_step": NEXT[p["kind"]]} for p in patterns]
    followups = [{"staff_id": p["staff_id"], "title": f"{NEXT[p['kind']]} ({p['staff_id']}, {p['store_id']})"}
                 for p in patterns]
    return ModelReply(text=json.dumps({"patterns": items, "followups": followups}))
