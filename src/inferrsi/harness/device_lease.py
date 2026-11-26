"""Host-local device leases. The key is the caller's device identity, not a CUDA probe."""

import os
from contextlib import AbstractContextManager
from pathlib import Path, PureWindowsPath

from .records.artifact_primitives import file_lock


class LeaseError(RuntimeError):
    """The device identity cannot be used for a lease."""


def _reserved_windows_name(device_id: str) -> bool:
    is_reserved = getattr(os.path, "isreserved", None)
    if is_reserved is not None:
        return is_reserved(device_id)
    return PureWindowsPath(device_id).is_reserved()


def _validate_device_id(device_id: str) -> None:
    if (
        not isinstance(device_id, str)
        or device_id in {"", ".", ".."}
        or any(char in device_id for char in "/\\\0")
    ):
        raise LeaseError("device identity must be a single path segment")
    if os.name == "nt" and (
        device_id.endswith((".", " "))
        or any(char in '<>:"|?*' or ord(char) < 32 for char in device_id)
        or _reserved_windows_name(device_id)
    ):
        raise LeaseError("device identity must be a valid Windows path segment")


class _Held:
    def __init__(self, lock: AbstractContextManager[None]) -> None:
        self._lock = lock

    def release(self) -> None:
        self._lock.__exit__(None, None, None)

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.release()


class DeviceLease:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def acquire(self, device_id: str) -> _Held:
        _validate_device_id(device_id)
        lock = file_lock(self.directory / device_id)
        try:
            lock.__enter__()
        except BlockingIOError:
            raise LeaseError(f"device busy: {device_id}") from None
        held = _Held(lock)
        try:
            if self._marker(device_id).exists():
                raise LeaseError(f"device quarantined: {device_id}")
        except BaseException:
            held.release()
            raise
        return held

    def quarantine(self, device_id: str, reason: str) -> None:
        """Refuse every later acquire of ``device_id`` until the marker file is removed.

        Call it while holding the lease, so no acquire can slip in before the marker.
        """
        _validate_device_id(device_id)
        self._marker(device_id).write_text(reason + "\n", encoding="utf-8")

    def _marker(self, device_id: str) -> Path:
        return self.directory / f"{device_id}.quarantined"
