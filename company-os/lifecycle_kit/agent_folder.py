"""Reads an agent folder: agent.md, instructions.md, guardrails.md, memory.md, graph.json and experience.md."""
import inspect
import json
from pathlib import Path

REQUIRED_FILES = ("agent.md", "instructions.md", "guardrails.md", "memory.md", "graph.json", "experience.md")
LIFECYCLE_STEPS = ("record", "understand", "decide", "check", "act", "remember")
FRONTMATTER_KEYS = ("name", "description", "family", "tools", "starter_roles", "approver_roles", "reads_library")
LIST_KEYS = ("tools", "starter_roles", "approver_roles")
MAX_LESSONS = 20   # the newest lessons win when experience.md holds more


def pack_folder(pack):
    """The folder of the module that defines the pack's class, or None."""
    try:
        return Path(inspect.getfile(type(pack))).resolve().parent
    except (TypeError, OSError):
        return None


def parse_value(raw):
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        return [part.strip().strip("\"'") for part in raw[1:-1].split(",") if part.strip()]
    if raw in ("true", "false"):
        return raw == "true"
    return raw.strip("\"'")


def parse_frontmatter(text):
    """Split `---` frontmatter (key: value lines, inline lists) from the body. Returns (dict, body)."""
    lines = text.strip("\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        return {}, text
    meta = {}
    for line in lines[1:end]:
        if ":" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition(":")
            meta[key.strip()] = parse_value(value)
    return meta, "\n".join(lines[end + 1:]).strip("\n")


def read_file(folder, name):
    path = Path(folder) / name
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def read_agent_md(folder):
    return parse_frontmatter(read_file(folder, "agent.md"))[0]


def read_graph(folder):
    text = read_file(folder, "graph.json")
    return json.loads(text) if text.strip() else {}


def bullets(text):
    """The text of every line that starts with `- `."""
    return [line[2:].strip() for line in text.split("\n") if line.startswith("- ") and line[2:].strip()]


def approved_lessons(folder, limit=MAX_LESSONS):
    return bullets(read_file(folder, "experience.md"))[-limit:]


def build_system_prompt(folder):
    """instructions.md, then the guardrails, then the approved lessons. Empty when the folder has no instructions."""
    if folder is None:
        return ""
    prompt = read_file(folder, "instructions.md").strip()
    if not prompt:
        return ""
    rules, lessons = bullets(read_file(folder, "guardrails.md")), approved_lessons(folder)
    if rules:
        prompt += "\n\nNever do these things:\n" + "\n".join(f"- {r}" for r in rules)
    if lessons:
        prompt += "\n\nLessons from past runs:\n" + "\n".join(f"- {x}" for x in lessons)
    return prompt


def check_agent_folder(folder, name=None, pack=None):
    """Return a list of problems with the folder. With `name` and `pack`, also compare agent.md with the pack."""
    folder, problems = Path(folder), []
    for file in REQUIRED_FILES:
        if not (folder / file).is_file():
            problems.append(f"missing {file}")
    if problems:
        return problems
    meta = read_agent_md(folder)
    problems += [f"agent.md has no {key}" for key in FRONTMATTER_KEYS if key not in meta]
    if not str(meta.get("description", "")).strip():
        problems.append("agent.md description is empty")
    for key in LIST_KEYS:
        if key in meta and not isinstance(meta[key], list):
            problems.append(f"agent.md {key} must be a list")
    if name is not None and meta.get("name") != name:
        problems.append(f"agent.md name {meta.get('name')!r} does not match {name!r}")
    if not read_file(folder, "instructions.md").strip():
        problems.append("instructions.md is empty")
    if not bullets(read_file(folder, "guardrails.md")):
        problems.append("guardrails.md has no bullet")
    if not read_file(folder, "memory.md").strip():
        problems.append("memory.md is empty")
    problems += _graph_problems(folder)
    if pack is not None:
        problems += _pack_problems(meta, pack)
    return problems


def _graph_problems(folder):
    try:
        graph = read_graph(folder)
    except ValueError as e:
        return [f"graph.json is not valid JSON: {e}"]
    steps = graph.get("steps") if isinstance(graph, dict) else None
    if not isinstance(steps, list) or [s.get("step") for s in steps if isinstance(s, dict)] != list(LIFECYCLE_STEPS):
        return [f"graph.json steps must be {', '.join(LIFECYCLE_STEPS)} in that order"]
    return [f"graph.json step {s['step']} has no text" for s in steps if not str(s.get("does", "")).strip()]


def _pack_problems(meta, pack):
    problems = []
    if meta.get("tools") != [spec.name for spec in pack.tools()]:
        problems.append("agent.md tools do not match the pack tools")
    for key in ("starter_roles", "approver_roles"):
        if set(meta.get(key, [])) != set(getattr(pack, key)):
            problems.append(f"agent.md {key} do not match the pack")
    if meta.get("reads_library") != bool(pack.reads_library):
        problems.append("agent.md reads_library does not match the pack")
    return problems
