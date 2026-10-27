"""Chat history: the earlier turns of one conversation become the first messages of the next run.
A turn is a person's prompt plus the final answer of that run. Old turns past the budget fold into one summary."""
from .compaction import INSTRUCTION, PREAMBLE, SUMMARY_CLOSE, SUMMARY_OPEN, _kept_facts, estimate_tokens

WINDOWS = {"fake": 200_000, "claude-cli": 200_000}   # model name -> context window in tokens
DEFAULT_WINDOW = 200_000
BUDGET_SHARE = 0.5          # history may use half of the window
SUMMARY_SHARE = 0.25        # of the budget, kept free for the summary when turns are folded
DIGEST_CHARS = 200


def window_for(model) -> int:
    return WINDOWS.get(model, DEFAULT_WINDOW)


def budget_for(model, window_tokens=None) -> int:
    window = min(window_for(model), window_tokens) if window_tokens else window_for(model)
    return int(window * BUDGET_SHARE)


def turn_tokens(turn) -> int:
    return (len(turn["prompt"]) + len(turn["answer"])) // 4


def earlier_turns(memory, ctx) -> list:
    """Oldest first. Only done runs of the same caller, in an area this run may read, with a prompt and an answer."""
    conversation_id = ctx.task.conversation_id
    if not conversation_id or not hasattr(memory, "conversation_runs"):
        return []
    areas = set(getattr(ctx.memory, "area_ids", None) or [ctx.task.area_id])
    turns = []
    for run in memory.conversation_runs(conversation_id):
        if (run["run_id"] == ctx.run_id or run["status"] != "done" or run["caller_id"] != ctx.task.caller_id
                or run["area_id"] not in areas):
            continue
        prompt, answer = "", ""
        for step in memory.run_steps(run["run_id"]):
            if step["step"] == "opened":
                prompt = str(step["detail"].get("prompt") or "")
            elif step["step"] == "closed":
                answer = str(step["detail"].get("final_text") or "")
        if prompt and answer:
            turns.append({"run_id": run["run_id"], "prompt": prompt, "answer": answer})
    return turns


def _pairs(turns) -> list:
    return [m for t in turns for m in ({"role": "user", "content": t["prompt"]},
                                       {"role": "assistant", "content": t["answer"]})]


def _digest(turns) -> str:
    """Code-made summary: one line per folded turn. It needs no model."""
    return "\n".join(f"- asked: {t['prompt'][:DIGEST_CHARS]!r}; answered: {t['answer'][:DIGEST_CHARS]!r}" for t in turns)


def build_history(turns, budget_tokens, summarise=None):
    """Return (messages, info). `summarise(messages) -> str | None` is optional; None or a failure uses the digest."""
    info = {"turns": len(turns), "summarised": False, "tokens": 0}
    if not turns:
        return [], info
    if sum(turn_tokens(t) for t in turns) <= budget_tokens:
        messages = _pairs(turns)
        info["tokens"] = estimate_tokens(messages)
        return messages, info
    room = int(budget_tokens * (1 - SUMMARY_SHARE))
    kept, used = [], 0
    for turn in reversed(turns):
        if kept and used + turn_tokens(turn) > room:
            break
        kept.insert(0, turn)   # the newest turn always stays, even if it alone is over budget
        used += turn_tokens(turn)
    folded = turns[:len(turns) - len(kept)]
    messages = _pairs(kept)
    if folded:
        old = _pairs(folded)
        body = None
        if summarise is not None:
            body = summarise([{"role": "user", "content": INSTRUCTION + "\n\n" + "\n".join(f"[{m['role']}] {m['content']}" for m in old)}])
        body = (str(body).strip() if body else "") or _digest(folded)
        body = body[:max(int(budget_tokens * SUMMARY_SHARE) * 4, DIGEST_CHARS)]
        framed = f"{PREAMBLE}\n\n{SUMMARY_OPEN}\n{body}\n\n{_kept_facts(old)}\n{SUMMARY_CLOSE}"
        messages = [{"role": "user", "content": framed}, *messages]
        info["summarised"] = True
    info["tokens"] = estimate_tokens(messages)
    return messages, info
