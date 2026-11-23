"""Capture a trusted local source entry without importing or executing worker code."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import input_binding

_MODULE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*", re.ASCII)


class EntryUnavailable(Exception):
    """The supported entry bytes cannot be resolved; no actual digest is known."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class EntryCaptureError(Exception):
    """A resolved entry could not be retained safely before execution."""


@dataclass(frozen=True)
class CapturedEntry:
    path: Path
    sha256: str
    size_bytes: int


def capture_module(root: Path, module: str, directory: Path) -> CapturedEntry:
    """Snapshot one source module from an explicit trusted root.

    The first CPU binding supports a standalone ``<module>.py`` entry. Dotted
    package names, bytecode/native modules and import hooks are not resolved by
    this port. In particular, neither a package initializer nor a worker module
    is imported to locate its code. The caller owns the private capture directory.
    """
    if not isinstance(module, str) or _MODULE.fullmatch(module) is None:
        raise EntryUnavailable("entry_kind_unsupported")
    name = module + ".py"
    try:
        stream = input_binding.open_regular(root, name)
    except (OSError, input_binding.BindingError):
        raise EntryUnavailable("entry_bytes_unavailable") from None
    destination = directory / name
    with stream:
        # A capture directory belongs to one registered attempt. Never replace
        # an existing entry snapshot on an interrupted or repeated operation.
        if destination.exists():
            raise EntryCaptureError("entry snapshot already exists")
        try:
            digest, size = input_binding.copy_stream(stream, destination)
            if input_binding.file_sha256(destination) != (digest, size):
                raise EntryCaptureError("entry snapshot differs from the captured bytes")
        except OSError as error:
            raise EntryCaptureError("entry snapshot could not be retained") from error
    return CapturedEntry(destination, digest, size)
