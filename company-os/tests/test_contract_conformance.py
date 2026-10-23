import unittest

from contract.conformance_tests import run_conformance
from core.fake_model import FakeModel
from core.model_gateway import Gateway
from core.agent_loop import Runtime


class _Memory:
    def __init__(self):
        self.n = 0

    def start_run(self, *a):
        self.n += 1
        return f"r{self.n}"

    def log_step(self, *a):
        pass

    def end_run(self, *a):
        pass

    def scoped(self, area_ids):
        return object()


class _AllowAll:
    def admit(self, task):
        from contract.types import ALLOW
        return ALLOW


def make_host(plugins, gate, replies):
    queue = list(replies)
    gw = Gateway({"fake": FakeModel({"conformance": lambda req: queue.pop(0)})})
    return Runtime(gw, _Memory(), gate or _AllowAll(), plugins)


class ConformanceTests(unittest.TestCase):
    def test_our_runtime_conforms(self):
        run_conformance(self, make_host)


if __name__ == "__main__":
    unittest.main()
