"""Shared plumbing for read tools: area guard, as_of date, argument checks, compact JSON replies."""
import json
import re
from datetime import date, timedelta

from contract.types import ToolSpec

from company_data.simulated_today import TODAY

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ToolInputError(Exception):
    """Raised by a handler for a bad argument or a denied area. Becomes an error JSON reply."""


def dumps(obj):
    return json.dumps(obj, separators=(",", ":"), default=str)


def error_reply(message):
    return dumps({"error": message})


def next_day(day):
    return (date.fromisoformat(day) + timedelta(days=1)).isoformat()


def days_before(day, n):
    return (date.fromisoformat(day) - timedelta(days=n)).isoformat()


def days_between(later, earlier):
    return (date.fromisoformat(later[:10]) - date.fromisoformat(earlier[:10])).days


def monday_of(day):
    d = date.fromisoformat(day[:10])
    return (d - timedelta(days=d.weekday())).isoformat()


def resolve_as_of(args, ctx):
    value = args.get("as_of") or ctx.task.inputs.get("as_of") or TODAY
    if not isinstance(value, str) or not DATE_RE.match(value):
        raise ToolInputError(f"as_of must look like YYYY-MM-DD, got {value!r}")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ToolInputError(f"as_of is not a real date: {value!r}")
    return value


def int_arg(args, name, default, low=1, high=366):
    value = args.get(name, default)
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ToolInputError(f"{name} must be a whole number")
    return max(low, min(high, value))


def str_arg(args, name):
    value = args.get(name)
    if value is not None and not isinstance(value, str):
        raise ToolInputError(f"{name} must be text")
    return value


def client_area_ids(data_conn):
    return {r["client_id"] for r in data_conn.execute("SELECT client_id FROM clients")}


def retail_area_ids(data_conn):
    return {r["client_id"] for r in data_conn.execute("SELECT DISTINCT client_id FROM stores")}


def build_tool(name, description, params, handler, *, area_ok, area_label, reads_outside_text=False):
    """Make a ToolSpec. `handler(args, area_id, as_of, ctx) -> JSON-able`. `area_ok(area_id) -> bool`."""
    def fn(args, ctx):
        args = args or {}
        area_id = ctx.task.area_id
        try:
            if not area_ok(area_id):
                raise ToolInputError(f"tool {name} is not available for area {area_id!r}; it serves {area_label}")
            for key in ("area_id", "client_id"):
                if args.get(key) not in (None, area_id):
                    raise ToolInputError(f"{key} {args[key]!r} is not the task's area {area_id!r}")
            as_of = resolve_as_of(args, ctx)
            return dumps(handler(args, area_id, as_of, ctx))
        except ToolInputError as exc:
            return error_reply(str(exc))

    schema = {"type": "object", "properties": {
        "as_of": {"type": "string", "description": "YYYY-MM-DD; rows after this date are hidden (default: the task's as_of, else today)"},
        **params}, "required": []}
    return ToolSpec(name=name, description=f"{description} Area: {area_label}.", params=schema, fn=fn,
                    reads_outside_text=reads_outside_text)
