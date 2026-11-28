"""Replay a completed profile from local, verified evidence."""

from __future__ import annotations

from pathlib import Path

from ..records import ProfileReceipt, read_retained_profile
from ..records.profile_evidence import decode_profile_trace


def replay_profile(root: Path, receipt: ProfileReceipt) -> dict:
    """Return the trace overview using the decoder recorded at capture time."""
    return decode_profile_trace(read_retained_profile(root, receipt), receipt)
