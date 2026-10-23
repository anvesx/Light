"""Action tools every pack may use. Each factory takes what the tool writes to and returns a ToolSpec."""
from contract.types import ToolSpec


def make_send_private_message(outbox) -> ToolSpec:
    def fn(args, ctx):
        msg_id = outbox.post(args["to_person_id"], args["text"], run_id=ctx.run_id,
                             agent=ctx.task.agent, kind=args.get("kind", "note"))
        return f"sent {msg_id}"
    return ToolSpec(
        name="send_private_message",
        description="Send a private message to one DevX person.",
        params={"type": "object", "required": ["to_person_id", "text", "kind"], "properties": {
            "to_person_id": {"type": "string"}, "text": {"type": "string"}, "kind": {"type": "string"}}},
        fn=fn)


def make_create_followup_task(memory_store) -> ToolSpec:
    def fn(args, ctx):
        item_id = memory_store.add_item(
            args["area_id"], "task", args["title"], status="open", source=f"agent:{ctx.task.agent}",
            source_ref=ctx.run_id, owner_id=args.get("owner_id"))
        return f"created {item_id}"
    return ToolSpec(
        name="create_followup_task",
        description="Write a follow-up task into company memory. Waits for approval.",
        params={"type": "object", "required": ["area_id", "title", "owner_id"], "properties": {
            "area_id": {"type": "string"}, "title": {"type": "string"}, "owner_id": {"type": "string"}}},
        fn=fn, risky=True)
