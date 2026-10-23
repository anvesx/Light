"""Cap a tool result so one tool cannot flood the model's context."""

MAX_CHARS = 8000
_NOTE_ROOM = 80


def cap_output(text: str, limit: int = MAX_CHARS) -> str:
    """Result is never longer than `limit`, including the note about what was cut."""
    if len(text) <= limit:
        return text
    keep = limit - _NOTE_ROOM
    return text[:keep] + f"\n[cut: {len(text) - keep} of {len(text)} characters removed]"
