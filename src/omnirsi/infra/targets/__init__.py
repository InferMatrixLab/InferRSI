"""Target repository inspection; adapters do not own experiment ordering."""

from .git import repository_identity, source_snapshot

__all__ = ["repository_identity", "source_snapshot"]
