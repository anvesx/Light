"""Company brain: a source-linked store of what the company knows, one area per client, plus a redacted playbook library."""
from .brain_store import BrainStore
from .scoped_brain import ScopedBrain

__all__ = ["BrainStore", "ScopedBrain"]
