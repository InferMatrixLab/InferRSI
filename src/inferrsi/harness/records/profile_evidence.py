"""Immutable raw profile evidence attached to a completed capture."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .optimization_log import read_regular
from .profile_timeline import publish_immutable_profile_artifact

_MAX_RAW_BYTES = 64 << 20
_DECODER_VERSIONS = {"chrome-trace-json-v1", "chrome-trace-gzip-v1"}


def _identifier(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or not value.isprintable()
        or len(value) > 256
    ):
        raise ValueError("invalid profile identity or metric")


def _utc(value: str) -> datetime:
    if not isinstance(value, str) or "T" not in value or len(value) > 40:
        raise ValueError("invalid profile timestamp")
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() != timedelta(0):
        raise ValueError("profile timestamps must use UTC")
    return stamp


@dataclass(frozen=True)
class ProfileReceipt:
    """Identity and capture window supplied by the capture adapter."""

    capture_id: str
    attempt_id: str
    service_id: str
    revision: str
    metric: str
    unit: str
    capture_started_at: str
    capture_ended_at: str
    artifact_ready_at: str
    raw_sha256: str
    decoder_version: str
    supersedes_capture_id: str | None = None

    def __post_init__(self) -> None:
        for value in (
            self.capture_id,
            self.attempt_id,
            self.service_id,
            self.revision,
            self.metric,
            self.unit,
        ):
            _identifier(value)
        if self.supersedes_capture_id is not None:
            _identifier(self.supersedes_capture_id)
            if self.supersedes_capture_id == self.capture_id:
                raise ValueError("profile recapture requires a new capture ID")
        if not isinstance(self.raw_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", self.raw_sha256
        ):
            raise ValueError("invalid raw profile digest")
        if (
            not isinstance(self.decoder_version, str)
            or self.decoder_version not in _DECODER_VERSIONS
        ):
            raise ValueError("unknown profile decoder version")
        if (
            not _utc(self.capture_started_at)
            <= _utc(self.capture_ended_at)
            <= _utc(self.artifact_ready_at)
        ):
            raise ValueError("invalid profile capture window")


def _directory(root: Path) -> Path:
    directory = root.resolve(strict=True) / "profile-evidence"
    if directory.resolve() != directory:
        raise ValueError("unsafe profile evidence directory")
    return directory


def _receipt_path(directory: Path, capture_id: str) -> Path:
    identity = hashlib.sha256(capture_id.encode()).hexdigest()
    return directory / f"{identity}.receipt.json"


def _receipt_bytes(receipt: ProfileReceipt) -> bytes:
    return json.dumps(
        asdict(receipt), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def _verified_raw(path: Path, digest: str) -> bytes:
    raw = read_regular(path, _MAX_RAW_BYTES)
    if not raw or len(raw) > _MAX_RAW_BYTES or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("raw profile does not match its receipt")
    return raw


def retain_profile(root: Path, source: Path, receipt: ProfileReceipt) -> None:
    """Publish verified raw bytes, then commit the immutable capture binding."""
    directory = _directory(root)
    destination = _receipt_path(directory, receipt.capture_id)
    binding = _receipt_bytes(receipt)
    if destination.exists() and read_regular(destination, 16384) != binding:
        raise ValueError("profile capture ID already has a different binding")
    if receipt.supersedes_capture_id is not None:
        # Preserve the link even if the earlier raw artifact is now unavailable.
        previous = _receipt_path(directory, receipt.supersedes_capture_id)
        original = ProfileReceipt(**json.loads(read_regular(previous, 16384)))
        if original.capture_id != receipt.supersedes_capture_id or _utc(
            original.capture_ended_at
        ) > _utc(receipt.capture_started_at):
            raise ValueError("profile recapture refers to a different capture")
    raw = _verified_raw(source, receipt.raw_sha256)
    directory.mkdir(exist_ok=True)
    publish_immutable_profile_artifact(directory / f"{receipt.raw_sha256}.raw", raw)
    publish_immutable_profile_artifact(destination, binding)


def read_retained_profile(root: Path, receipt: ProfileReceipt) -> bytes:
    """Verify both the immutable identity binding and the retained raw bytes."""
    directory = _directory(root)
    recorded = read_regular(_receipt_path(directory, receipt.capture_id), 16384)
    if recorded != _receipt_bytes(receipt):
        raise ValueError("retained profile identity does not match its receipt")
    return _verified_raw(directory / f"{receipt.raw_sha256}.raw", receipt.raw_sha256)
