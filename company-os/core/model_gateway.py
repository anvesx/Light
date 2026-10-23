"""AI gateway: the only path to a model. Routes by model name, counts cache and cost, enforces budgets."""
from dataclasses import replace

from contract.types import ModelReply, ModelRequest, Usage

from .cost_ledger import CostLedger
from .fixed_clock import FixedClock
from .model_prices import cost_usd
from .prompt_cache import PromptCache, prefix_parts


class BudgetExceeded(Exception):
    pass


class TransientModelError(Exception):
    """A failure worth retrying (timeout, overload)."""


class Gateway:
    def __init__(self, backends: dict, ledger=None, cache=None, clock=None):
        self._backends = backends
        self.ledger = ledger or CostLedger()
        self.cache = cache or PromptCache()
        self.clock = clock or FixedClock()

    def budget_left(self, agent: str, caller_id: str) -> float:
        return min(self.ledger.budget_left(f"agent:{agent}"), self.ledger.budget_left(f"caller:{caller_id}"))

    def call(self, req: ModelRequest, *, agent: str, caller_id: str, area_id: str, run_id: str) -> ModelReply:
        if self.budget_left(agent, caller_id) <= 0:
            raise BudgetExceeded(f"budget spent for agent {agent!r} or caller {caller_id!r}")
        backend = self._backends.get(req.model)
        if backend is None:
            raise KeyError(f"no backend for model {req.model!r}")
        reply = backend.complete(req, agent)
        usage, cache = self._account_cache(req, agent, reply.usage)
        cost = cost_usd(req.model, usage)
        self.ledger.record(agent=agent, caller_id=caller_id, area_id=area_id, run_id=run_id,
                           model=req.model, usage=usage, cost_usd=cost, cache=cache)
        return replace(reply, usage=usage, cost_usd=cost, cache_hit=(cache == "hit"))

    def _account_cache(self, req: ModelRequest, agent: str, usage: Usage):
        if not req.cache_prefix:
            return usage, "none"
        parts = prefix_parts(req.system, req.tools)
        prefix_text = parts["system"] + parts["tools"]
        cache = self.cache.check(agent, prefix_text, self.clock.now, parts)
        prefix_tokens = min(len(prefix_text) // 4, usage.input_tokens)
        moved = replace(usage, input_tokens=usage.input_tokens - prefix_tokens)
        if cache == "hit":
            moved.cache_read_tokens = prefix_tokens
        else:
            moved.cache_write_tokens = prefix_tokens
        return moved, cache
