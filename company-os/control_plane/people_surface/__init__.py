"""Where agents reach people: a private message outbox and an approval queue."""
from pathlib import Path

DB_PATH = str(Path(__file__).parent / "people_surface.db")

from .approval_queue import Approvals  # noqa: E402
from .private_outbox import Outbox  # noqa: E402

__all__ = ["Outbox", "Approvals", "DB_PATH"]
