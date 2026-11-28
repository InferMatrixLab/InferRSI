"""Replay a completed profile from local, verified evidence."""

from __future__ import annotations

from pathlib import Path

from ..records import ProfileReceipt, read_retained_profile
from ..records.profile_timeline import compile_profile_trace


def replay_profile(root: Path, receipt: ProfileReceipt) -> dict:
    """Return the trace overview using the decoder recorded at capture time."""
    raw = read_retained_profile(root, receipt)
    try:
        overview, _ = compile_profile_trace(raw, receipt.decoder_version == "chrome-trace-gzip-v1")
    except EOFError as exc:
        raise ValueError("truncated compressed profile") from exc
    return overview
