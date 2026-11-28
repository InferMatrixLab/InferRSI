"""Durable launch facts for recoverable optimization attempts."""

import os
import sys
from datetime import datetime, timezone
from itertools import count
from pathlib import Path

from ..records.artifact_primitives import digest
from ..records.atomic_json import durable_write_json


def linux_process_domain() -> tuple[str | None, str | None]:
    if sys.platform != "linux":
        return None, None
    try:
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
        namespace = os.readlink("/proc/self/ns/pid")
    except (OSError, UnicodeError):
        return None, None
    return boot_id or None, namespace or None


class LaunchRecord:
    """Publish intent before spawning and retain the supervisor's observations."""

    def __init__(self, path: Path, argv: list[str]):
        self.path = path
        boot_id, namespace = linux_process_domain()
        self.record = {
            "schema_version": 1,
            "stage": path.stem,
            "state": "intent",
            "argv_sha256": digest(argv),
            "platform": sys.platform,
            "intent_at": datetime.now(timezone.utc).isoformat(),
            "boot_id": boot_id,
            "pid_namespace": namespace,
        }
        durable_write_json(path, self.record, exclusive=True)

    @classmethod
    def numbered(cls, directory: Path, stage: str, argv: list[str]) -> "LaunchRecord":
        for index in count(1):
            try:
                return cls(directory / f"{stage}-{index:04d}.json", argv)
            except FileExistsError:
                continue

    def launched(self, run: dict) -> None:
        self.record.update(
            state="launched", spawned=True, pid=run["pid"],
            process_group_id=run["process_group_id"], started_at=run["started_at"],
        )
        durable_write_json(self.path, self.record)

    def ended(self, run: dict, spawned: bool | None) -> None:
        self.record.update(
            state="ended", spawned=spawned, pid=run["pid"],
            process_group_id=run["process_group_id"], started_at=run["started_at"],
            ended_at=run["ended_at"], status=run["status"], domain_empty=run["domain_empty"],
        )
        durable_write_json(self.path, self.record)


def observe(record: dict) -> str:
    """Use an empty-group probe only within its recorded Linux boot and PID namespace."""
    state = record.get("state")
    if state == "intent":
        return "launch_unconfirmed"
    if state not in ("launched", "ended"):
        return "invalid_record"
    pid, group = record.get("pid"), record.get("process_group_id")
    if state == "ended" and record.get("spawned") is False:
        return "not_spawned" if pid is None and group is None else "invalid_record"
    if record.get("spawned") is not True or type(pid) is not int or pid <= 0:
        return "launch_unconfirmed"
    if state == "ended" and record.get("domain_empty") is True:
        return "recorded_empty"
    if (record.get("platform") != "linux" or sys.platform != "linux"
            or type(group) is not int or group != pid):
        return "unobservable"
    boot_id, namespace = linux_process_domain()
    if (not boot_id or not namespace or boot_id != record.get("boot_id")
            or namespace != record.get("pid_namespace")):
        return "unobservable"
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return "observed_empty"
    except OSError:
        return "unobservable"
    return "live"
