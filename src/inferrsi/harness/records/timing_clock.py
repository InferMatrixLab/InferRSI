"""Parse the timestamps stored in profile reviews and experiment timing ledgers."""
from __future__ import annotations

import re
from datetime import datetime, timezone

_STAMP = re.compile(
    r"(?P<clock>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}|\d{8}T\d{6})"
    r"(?:\.(?P<fraction>\d{1,6}))?(?P<zone>Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)", re.ASCII
)


def recorded_time(value: object) -> datetime:
    match = _STAMP.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise ValueError("expected a date and time with seconds and a UTC offset")
    clock = match["clock"]
    if "-" not in clock:  # Compatibility with compact timestamps accepted by earlier writers.
        clock = datetime.strptime(clock, "%Y%m%dT%H%M%S").isoformat()
    fraction = (match["fraction"] or "").ljust(6, "0")
    offset = "+00:00" if match["zone"] == "Z" else match["zone"]
    try:
        return datetime.fromisoformat(f"{clock}.{fraction}{offset}").astimezone(timezone.utc)
    except OverflowError as exc:
        raise ValueError("timestamp is outside the UTC date range") from exc
