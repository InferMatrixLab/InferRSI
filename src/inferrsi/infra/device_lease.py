"""Host-local device leases. The key is the caller's device identity, not a CUDA probe."""

import fcntl
from pathlib import Path


class LeaseError(RuntimeError):
    """The device identity is already held."""


class _Held:
    def __init__(self, handle) -> None:
        self._handle = handle

    def release(self) -> None:
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.release()


class DeviceLease:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def acquire(self, device_id: str) -> _Held:
        if not device_id or any(char in device_id for char in "/\\"):
            raise LeaseError("device identity must be a single path segment")
        handle = (self.directory / device_id).open("a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            raise LeaseError(f"device busy: {device_id}") from None
        if self._marker(device_id).exists():
            _Held(handle).release()
            raise LeaseError(f"device quarantined: {device_id}")
        return _Held(handle)

    def quarantine(self, device_id: str, reason: str) -> None:
        """Refuse every later acquire of ``device_id`` until the marker file is removed.

        Call it while holding the lease, so no acquire can slip in before the marker.
        """
        self._marker(device_id).write_text(reason + "\n", encoding="utf-8")

    def _marker(self, device_id: str) -> Path:
        return self.directory / f"{device_id}.quarantined"
