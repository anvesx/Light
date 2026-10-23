"""Builds the whole Company OS in one place, so the demo, the console, the exams and the tests all wire it the same way.

Agent packs are found through wiring/agent_registry.py: pack.py has make_pack(parts) and fake_brain.py has brain(request).
"""
import importlib
import os
import tempfile
from dataclasses import dataclass, field

from control_plane.company_brain import BrainStore
from company_data import DB_PATH as DATA_DB, connect
from company_data.generate_dummy_data import build as build_dummy_data
from control_plane.company_memory import MemoryStore
from control_plane.connectors.meetings_to_memory import sync_meetings
from control_plane.connectors.people_directory import PeopleDirectory
from core.claude_cli_model import ClaudeCliModel
from core.cost_ledger import CostLedger
from core.fake_model import FakeModel
from core.model_gateway import Gateway
from core.prompt_cache import PromptCache
from control_plane.guardrails.access_policy import AccessPolicy
from control_plane.guardrails.every_action_check import ActionGuard
from control_plane.guardrails.tool_scope import ToolScope
from control_plane.guardrails.way_in_check import WayInCheck
from lifecycle_kit.lifecycle_runner import LifecycleRunner
from control_plane.people_surface.approval_queue import Approvals
from control_plane.people_surface.private_outbox import Outbox
from core.agent_loop import Runtime
from control_plane.triggers.simulated_clock import Clock
from wiring.agent_registry import AGENTS, available_agents

ALL_AGENTS = tuple(AGENTS)


@dataclass
class Parts:
    """What an agent pack gets when it is built: the data, the memory and the outbox."""
    data_conn: object
    memory: object
    outbox: object
    directory: object
    clock: object
    brain: object = None


@dataclass
class CompanyOS:
    data_conn: object
    memory: object
    outbox: object
    approvals: object
    clock: object
    directory: object
    policy: object
    ledger: object
    gateway: object
    runtime: object
    runner: object
    way_in: object
    packs: dict = field(default_factory=dict)
    state_dir: str = ""
    brain: object = None

    def run(self, agent, caller_id, area_id, trigger_kind="request", inputs=None, model="fake"):
        """Start one agent run through the lifecycle runner (the way-in check runs inside)."""
        from contract.types import Task
        task = Task(agent=agent, caller_id=caller_id, area_id=area_id, trigger_kind=trigger_kind,
                    inputs=inputs or {}, model=model)
        return self.runner.run(self.packs[agent], task)


def build_company_os(agents=None, *, state_dir=None, data_db=DATA_DB, now="2026-10-19T09:00",
                     extra_backends=None, real_model=None, seed_brain=False) -> CompanyOS:
    if not os.path.exists(data_db):
        build_dummy_data(data_db)
    state_dir = state_dir or tempfile.mkdtemp(prefix="company_os_")
    os.makedirs(state_dir, exist_ok=True)
    clock = Clock(now)
    data_conn = connect(data_db)
    memory = MemoryStore(os.path.join(state_dir, "company_memory.db"), clock=clock)
    outbox = Outbox(os.path.join(state_dir, "people_surface.db"), clock=clock)
    approvals = Approvals(os.path.join(state_dir, "people_surface.db"), clock=clock)
    for r in data_conn.execute("SELECT client_id, name FROM clients"):
        memory.ensure_area(r["client_id"], name=r["name"], kind="client")
    memory.ensure_area("devx-internal", name="DevX internal", kind="internal")
    memory.ensure_area("hold", name="Waiting for a person to sort", kind="hold")
    sync_meetings(data_conn, memory, until=now)

    directory = PeopleDirectory(data_conn)
    brain = BrainStore(memory, data_conn)
    parts = Parts(data_conn, memory, outbox, directory, clock, brain)
    packs, brains = {}, {}
    importable = available_agents()[0]
    for name in (importable if agents is None else [n for n in agents if n in importable]):  # None: every available agent
        packs[name] = importlib.import_module(f"{AGENTS[name]}.pack").make_pack(parts)
        brains[name] = importlib.import_module(f"{AGENTS[name]}.fake_brain").brain

    policy = AccessPolicy()
    ledger = CostLedger()
    backends = {"fake": FakeModel(brains), **(extra_backends or {})}
    if real_model == "claude-cli":   # opt in to the real model; the default stays fake
        backends["claude-cli"] = ClaudeCliModel()
    gateway = Gateway(backends, ledger=ledger, cache=PromptCache(), clock=clock)
    way_in = WayInCheck(directory, gateway, policy)
    runtime = Runtime(gateway, memory, way_in, plugins=[ToolScope(policy), ActionGuard(policy, approvals, directory, memory)],
                      clock=clock)
    for pack in packs.values():
        pack.register(runtime, policy)
    cos = CompanyOS(data_conn, memory, outbox, approvals, clock, directory, policy, ledger, gateway, runtime,
                    LifecycleRunner(runtime), way_in, packs, state_dir, brain)
    if seed_brain and "brain_cleaner" in packs:  # the brain starts filled: records, then every history source
        from control_plane.company_brain import pipeline
        from control_plane.company_brain.record_sync import sync_records
        sync_records(data_conn, brain, until=now[:10])
        pipeline.ingest_manifest(cos, history=True)
    return cos
