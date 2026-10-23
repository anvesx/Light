"""Cost ledger: one row per model call, plus budgets per agent or per caller."""
import math


class CostLedger:
    def __init__(self):
        self.entries = []
        self._budgets = {}

    def record(self, *, agent, caller_id, area_id, run_id, model, usage, cost_usd, cache) -> dict:
        row = {"agent": agent, "caller_id": caller_id, "area_id": area_id, "run_id": run_id,
               "model": model, "usage": usage, "cost_usd": cost_usd, "cache": cache}
        self.entries.append(row)
        return row

    def set_budget(self, key: str, usd: float) -> None:
        self._budgets[key] = usd

    def spent(self, key: str) -> float:
        kind, _, value = key.partition(":")
        field = {"agent": "agent", "caller": "caller_id"}[kind]
        return sum(e["cost_usd"] for e in self.entries if e[field] == value)

    def budget_left(self, key: str) -> float:
        """Unlimited (infinity) when no budget is set."""
        if key not in self._budgets:
            return math.inf
        return self._budgets[key] - self.spent(key)
