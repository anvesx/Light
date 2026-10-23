import unittest

from contract.types import ModelReply, ModelRequest, ToolSpec, Usage
from core.cost_ledger import CostLedger
from core.fake_model import FakeModel
from core.fixed_clock import FixedClock
from core.model_gateway import BudgetExceeded, Gateway
from core.model_prices import cost_usd
from core.prompt_cache import PromptCache


def tool(name="a"):
    return ToolSpec(name, "does " + name, {"type": "object", "properties": {}})


def req(system="You help.", tools=None, model="fake"):
    return ModelRequest(model=model, system=system, messages=[{"role": "user", "content": "hi"}],
                        tools=tools if tools is not None else [tool("b"), tool("a")])


def make(clock=None):
    brain = lambda r: ModelReply(text="hello there")
    return Gateway({"fake": FakeModel({"ag": brain}), "other": FakeModel({"ag": lambda r: ModelReply(text="other")})},
                   clock=clock or FixedClock())


def call(gw, r, agent="ag", caller="P01"):
    return gw.call(r, agent=agent, caller_id=caller, area_id="C01", run_id="r1")


class PriceTests(unittest.TestCase):
    def test_table(self):
        self.assertAlmostEqual(cost_usd("opus-5-5", Usage(1_000_000, 1_000_000)), 24.0)
        self.assertAlmostEqual(cost_usd("opus-5-5", Usage(cache_read_tokens=1_000_000)), 0.4)
        self.assertAlmostEqual(cost_usd("opus-5-5", Usage(cache_write_tokens=1_000_000)), 5.0)
        self.assertAlmostEqual(cost_usd("haiku-5-5", Usage(1_000_000, 1_000_000)), 0.6)
        self.assertEqual(cost_usd("fake", Usage(1000, 1000)), cost_usd("sonnet-5-5", Usage(1000, 1000)))


class GatewayTests(unittest.TestCase):
    def test_cost_comes_from_price_table_and_is_ledgered(self):
        gw = make()
        reply = call(gw, req())
        self.assertEqual(reply.text, "hello there")
        self.assertGreater(reply.cost_usd, 0)
        row = gw.ledger.entries[0]
        self.assertEqual(row["cost_usd"], cost_usd("fake", row["usage"]))
        self.assertEqual((row["agent"], row["caller_id"], row["area_id"], row["run_id"], row["model"]),
                         ("ag", "P01", "C01", "r1", "fake"))
        self.assertEqual(len(gw.ledger.entries), 1)
        call(gw, req())
        self.assertEqual(len(gw.ledger.entries), 2)

    def test_cache_write_then_hit_then_expiry(self):
        clock = FixedClock()
        gw = make(clock)
        self.assertEqual(call(gw, req()).cache_hit, False)
        clock.advance(4)
        second = call(gw, req())
        self.assertTrue(second.cache_hit)
        self.assertEqual([e["cache"] for e in gw.ledger.entries], ["write", "hit"])
        self.assertGreater(gw.ledger.entries[0]["usage"].cache_write_tokens, 0)
        self.assertGreater(gw.ledger.entries[1]["usage"].cache_read_tokens, 0)
        self.assertLess(gw.ledger.entries[1]["cost_usd"], gw.ledger.entries[0]["cost_usd"])
        clock.advance(6)
        call(gw, req())
        self.assertEqual(gw.ledger.entries[-1]["cache"], "write")
        self.assertEqual(gw.cache.log[-1]["changed"], ["expired"])

    def test_miss_names_changed_part(self):
        gw = make()
        call(gw, req())
        call(gw, req(system="Different system."))
        self.assertEqual(gw.cache.log[-1]["changed"], ["system"])
        call(gw, req(system="Different system.", tools=[tool("zzz")]))
        self.assertEqual(gw.cache.log[-1]["changed"], ["tools"])

    def test_tool_order_does_not_change_prefix(self):
        gw = make()
        call(gw, req(tools=[tool("a"), tool("b")]))
        call(gw, req(tools=[tool("b"), tool("a")]))
        self.assertEqual(gw.ledger.entries[-1]["cache"], "hit")

    def test_cache_is_per_agent(self):
        cache = PromptCache()
        now = "2026-10-19T09:00"
        self.assertEqual(cache.check("x", "p", now), "write")
        self.assertEqual(cache.check("y", "p", now), "write")
        self.assertEqual(cache.check("x", "p", now), "hit")

    def test_budget_refusal(self):
        gw = make()
        gw.ledger.set_budget("agent:ag", 0.0)
        with self.assertRaises(BudgetExceeded):
            call(gw, req())
        self.assertEqual(gw.ledger.entries, [])
        gw2 = make()
        first = call(gw2, req())
        gw2.ledger.set_budget("caller:P01", first.cost_usd)
        self.assertEqual(gw2.budget_left("ag", "P01"), 0)
        with self.assertRaises(BudgetExceeded):
            call(gw2, req())
        call(gw2, req(), caller="P02")

    def test_ledger_budget_math(self):
        led = CostLedger()
        self.assertEqual(led.budget_left("agent:x"), float("inf"))
        led.set_budget("agent:x", 1.0)
        led.record(agent="x", caller_id="c", area_id="a", run_id="r", model="fake",
                   usage=Usage(), cost_usd=0.25, cache="none")
        self.assertEqual(led.spent("agent:x"), 0.25)
        self.assertEqual(led.budget_left("agent:x"), 0.75)
        self.assertEqual(led.spent("caller:c"), 0.25)

    def test_routing_by_model(self):
        gw = make()
        self.assertEqual(call(gw, req(model="fake")).text, "hello there")
        with self.assertRaises(KeyError):
            call(gw, req(model="nope"))
        gw2 = Gateway({"haiku-5-5": FakeModel({"ag": lambda r: ModelReply(text="from haiku")})})
        reply = call(gw2, req(model="haiku-5-5"))
        self.assertEqual(reply.text, "from haiku")
        self.assertEqual(gw2.ledger.entries[0]["model"], "haiku-5-5")

    def test_runtime_object_holds_no_backend(self):
        from core.agent_loop import Runtime
        gw = make()
        rt = Runtime(gw, object(), object())
        held = list(vars(rt).values())
        self.assertIn(gw, held)
        self.assertFalse(any(isinstance(v, FakeModel) for v in held))
        self.assertFalse(hasattr(rt, "backends"))


if __name__ == "__main__":
    unittest.main()
