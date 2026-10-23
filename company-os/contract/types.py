"""Shared data shapes. Every module imports these, so keep them small and stable."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass
class ToolSpec:
    name: str
    description: str
    params: dict                      # JSON-schema style: {"type": "object", "properties": {...}, "required": [...]}
    fn: Any = None                    # fn(args: dict, ctx: RunContext) -> str
    risky: bool = False               # risky tools wait for a person's approval
    reads_outside_text: bool = False  # result holds client or outside text: treat it as data, never as orders


@dataclass
class ModelRequest:
    model: str                 # "fake", "claude-cli", or a price-table name such as "sonnet-5-5"
    system: str
    messages: list             # dicts: {"role": "user"|"assistant"|"tool", "content": str, ...}
    tools: list                # list of ToolSpec, sorted by name so the cached prefix stays the same
    effort: str = "medium"
    cache_prefix: bool = True  # system + tools form the cacheable prefix


@dataclass
class ModelReply:
    text: str = ""
    tool_calls: list = field(default_factory=list)   # list of ToolCall
    usage: Usage = field(default_factory=Usage)
    cost_usd: float = 0.0
    cache_hit: bool = False


@dataclass
class Task:
    agent: str                 # pack name, e.g. "meeting_prep"
    caller_id: str             # person_id of who or what started it ("system" for timers)
    area_id: str               # the one memory area this run may read: a client_id or "devx-internal"
    trigger_kind: str          # "timer" | "request" | "event" | "test"
    prompt: str = ""
    inputs: dict = field(default_factory=dict)
    max_steps: int = 12
    model: str = "fake"


@dataclass
class Decision:
    verdict: str               # "allow" | "ask" | "deny"
    reason: str = ""


ALLOW = Decision("allow")


@dataclass
class RunContext:
    run_id: str
    task: Task
    memory: Any                # ScopedMemory: can read only task.area_id
    status: str = "running"
    held: list = field(default_factory=list)    # approval ids waiting for a person
    notes: dict = field(default_factory=dict)   # free space for the kit and packs


@dataclass
class RunResult:
    run_id: str
    status: str                # "done" | "refused" | "held" | "failed" | "max_steps"
    final_text: str = ""
    tool_results: list = field(default_factory=list)   # dicts: {"call": ToolCall, "result": str, "verdict": str}
    cost_usd: float = 0.0
    reason: str = ""
