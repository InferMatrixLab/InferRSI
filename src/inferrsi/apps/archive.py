"""Publish and read the standardized Apps output in an authorized workspace."""

import ctypes
import errno
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from inferrsi._json_v1 import decode, encode

from .result import publication_error, validate_result

_OUTPUT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_RESERVED_NAMES = re.compile(r"CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9]", re.IGNORECASE)


@dataclass(frozen=True)
class RunOutput:
    """The Apps result and the location of its publication, if successful."""

    output_id: str
    directory: Path | None
    result: dict


def validate_output_id(output_id: str) -> None:
    if (
        not isinstance(output_id, str)
        or not _OUTPUT_ID.fullmatch(output_id)
        or output_id.endswith(".")
        or _RESERVED_NAMES.fullmatch(output_id.split(".", 1)[0])
    ):
        raise ValueError("output_id must be a portable directory name")


def _output_root(workspace: Path, *, create: bool) -> Path:
    root = Path(workspace).resolve(strict=True) / "output"
    if root.is_symlink() or root.resolve() != root:
        raise OSError("invalid Apps output root")
    if create:
        root.mkdir(exist_ok=True)
    return root


def _result_entry(data: bytes) -> dict:
    return {
        "path": "result.json",
        "sha256": sha256(data).hexdigest(),
        "size_bytes": len(data),
        "media_type": "application/json",
    }


def _manifest(output_id: str, created_at: str, result: dict, entry: dict) -> dict:
    return {
        "schema_version": 1,
        "output_id": output_id,
        "created_at": created_at,
        "operation": result["operation"],
        "run_id": result["execution"]["run_id"] if result["execution"] is not None else None,
        "attempt_id": result["attempt_id"],
        "result": entry,
    }


def _read_file(path: Path) -> bytes:
    if path.resolve(strict=True) != path or not path.is_file():
        raise ValueError("expected a regular Apps output file")
    return path.read_bytes()


def _read_output(directory: Path, output_id: str) -> dict:
    if directory.resolve(strict=True) != directory or not directory.is_dir():
        raise ValueError("expected an Apps output directory")
    manifest_data = _read_file(directory / "manifest.json")
    manifest = decode(manifest_data)
    if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int:
        raise ValueError("invalid Apps output manifest")
    if manifest["schema_version"] != 1:
        raise ValueError("unsupported Apps output manifest version")
    created_at = manifest.get("created_at")
    if not isinstance(created_at, str) or not created_at.endswith("Z") or "T" not in created_at:
        raise ValueError("invalid Apps output creation time")
    datetime.fromisoformat(created_at[:-1] + "+00:00")

    entry = manifest.get("result")
    if not isinstance(entry, dict) or entry.get("path") != "result.json":
        raise ValueError("invalid Apps manifest result path")
    data = _read_file(directory / "result.json")
    expected_entry = _result_entry(data)
    if entry != expected_entry:
        raise ValueError("Apps output manifest does not match result.json bytes")
    result = decode(data)
    validate_result(result)
    if manifest_data != encode(_manifest(output_id, created_at, result, expected_entry)):
        raise ValueError("Apps output manifest does not match result.json")
    return result


def read_result(workspace: Path, output_id: str) -> RunOutput:
    """Read the named publication, checking its version, metadata and result bytes."""
    validate_output_id(output_id)
    directory = _output_root(workspace, create=False) / output_id
    return RunOutput(output_id, directory, _read_output(directory, output_id))


def _write_file(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _publish_directory(staging: Path, destination: Path) -> None:
    """Atomically publish a complete directory without replacing any entry."""
    if os.name == "nt":
        staging.rename(destination)
        return

    libc = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(staging)
    target = os.fsencode(destination)
    try:
        if sys.platform == "linux":
            at_fdcwd, rename_noreplace = -100, 1
            rename = libc.renameat2
            rename.argtypes = (
                ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint,
            )
            status = rename(at_fdcwd, source, at_fdcwd, target, rename_noreplace)
        elif sys.platform == "darwin":
            rename_excl = 0x00000004
            rename = libc.renamex_np
            rename.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
            status = rename(source, target, rename_excl)
        else:
            raise OSError(errno.ENOTSUP, "atomic no-replace directory rename is unavailable")
    except AttributeError as exc:
        raise OSError(errno.ENOTSUP, "atomic no-replace directory rename is unavailable") from exc
    if status != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def publish_result(workspace: Path, result: dict, *, output_id: str | None = None) -> RunOutput:
    """Publish an AppsResultV1 after the underlying operation has returned."""
    if output_id is None:
        output_id = uuid4().hex
    validate_output_id(output_id)
    validate_result(result)
    data = encode(result)
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    manifest = encode(_manifest(output_id, created_at, result, _result_entry(data)))

    try:
        root = _output_root(workspace, create=True)
        destination = root / output_id
        with TemporaryDirectory(prefix=".pending-", dir=root) as temporary:
            staging = Path(temporary)
            _write_file(staging / "result.json", data)
            _write_file(staging / "manifest.json", manifest)
            verified_result = _read_output(staging, output_id)
            _publish_directory(staging, destination)
    except (OSError, ValueError):
        return RunOutput(output_id, None, publication_error(result))
    return RunOutput(output_id, destination, verified_result)
