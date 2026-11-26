"""Read bounded service-reuse records and validate their retained paths and values."""

import json
import math
from pathlib import Path

JSON_SIZE_LIMIT = 4 * 1024 * 1024


def safe_path(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ValueError("Expected a campaign-relative path")
    part = Path(relative)
    if part.is_absolute() or ".." in part.parts:
        raise ValueError("Path must stay inside the campaign")
    target = root / part
    if any(
        p.is_symlink() for p in (target, *target.parents) if p.is_relative_to(root)
    ) or not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("Symbolic or escaping campaign path")
    return target


def no_fingerprints(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or any(
                name in key.lower() for name in ("sha256", "fingerprint", "digest")
            ):
                raise ValueError("File fingerprints are not part of the service-reuse protocol")
            no_fingerprints(item)
    elif isinstance(value, list):
        for item in value:
            no_fingerprints(item)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Nonfinite JSON value")


def read(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > JSON_SIZE_LIMIT:
        raise ValueError(f"Missing, symbolic or oversized JSON: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Result must be a JSON object")
        no_fingerprints(value)
    except RecursionError as error:
        raise ValueError(f"JSON nesting exceeds the supported depth: {path.name}") from error
    return value


def error_excerpt(message):
    return message if len(message) <= 1024 else message[:1021] + "..."
