# Harness-owned atomic JSON evidence writes. The bytes equal those written by
# inferrsi.apps.storage.artifacts.atomic_write_json; Harness does not import that module here.

import json
import os
import tempfile
import time
import uuid
from pathlib import Path

# Windows refuses os.replace while another handle holds the destination open.
# A bounded retry covers the observed contention without hiding a real failure.
REPLACE_ATTEMPTS = 8
REPLACE_DELAY_SECONDS = 0.05


def sync_directory(path: Path) -> None:
    if os.name == "posix":
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def atomic_write_json(path: Path, value: object) -> None:
    path = Path(path)
    # A per-writer temporary name keeps two writers from sharing one file.
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    try:
        for attempt in range(REPLACE_ATTEMPTS):
            try:
                temporary.replace(path)
                return
            except PermissionError:
                if attempt + 1 == REPLACE_ATTEMPTS:
                    raise
                time.sleep(REPLACE_DELAY_SECONDS)
    finally:
        if temporary.exists():
            temporary.unlink()


def durable_write_json(path: Path, value: object, *, exclusive: bool = False) -> None:
    """Flush a recovery record before publication and sync its directory."""
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    staged = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix=f"{path.name}.", suffix=".tmp", delete=False,
    )
    temporary = Path(staged.name)
    try:
        with staged as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            # Publish the complete file without replacing an earlier launch record.
            os.link(temporary, path)
        else:
            for attempt in range(REPLACE_ATTEMPTS):
                try:
                    temporary.replace(path)
                    break
                except PermissionError:
                    if attempt + 1 == REPLACE_ATTEMPTS:
                        raise
                    time.sleep(REPLACE_DELAY_SECONDS)
        sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)
