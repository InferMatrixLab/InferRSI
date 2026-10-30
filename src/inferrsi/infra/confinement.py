"""Filesystem confinement for candidate build and trial commands.

``execute_command`` is unchanged. The default backend uses a user and mount
namespace when the kernel allows it, and refuses to run otherwise. It does not
fall back to an unconfined subprocess. ``FixtureBackend`` only refuses argv
paths outside the writable set; it is a test double, not an OS boundary.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path


class ConfinementUnavailable(RuntimeError):
    """The command was not executed because confinement could not be enforced."""


def namespaces_available() -> bool:
    try:
        limit = int(Path("/proc/sys/user/max_user_namespaces").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return limit > 0


def _within(path: Path, roots: tuple[Path, ...]) -> bool:
    resolved = path.resolve()
    return any(resolved == root or root in resolved.parents for root in roots)


def _outside_writable(argv: tuple[str, ...], writable: tuple[Path, ...]) -> Path | None:
    for arg in argv[1:]:
        if not arg.startswith("/"):
            continue
        path = Path(arg)
        if not _within(path, writable):
            return path
    return None


def _run_local(argv: tuple[str, ...], cwd: Path, deadline: float) -> dict:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ConfinementUnavailable("execution deadline exhausted before start")
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=remaining,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        }
    status = "completed" if completed.returncode == 0 else "failed"
    return {
        "status": status,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


class UnavailableBackend:
    """Fail closed. Does not execute the candidate."""

    name = "unavailable"

    def run(
        self,
        argv: tuple[str, ...],
        cwd: Path,
        writable: tuple[Path, ...],
        readable: tuple[Path, ...],
        deadline: float,
    ) -> dict:
        del argv, cwd, writable, readable, deadline
        raise ConfinementUnavailable("confinement backend unavailable")


class FixtureBackend:
    """Refuse argv paths outside ``writable``. Not mount-namespace confinement."""

    name = "fixture"

    def run(
        self,
        argv: tuple[str, ...],
        cwd: Path,
        writable: tuple[Path, ...],
        readable: tuple[Path, ...],
        deadline: float,
    ) -> dict:
        del readable
        outside = _outside_writable(argv, writable)
        if outside is not None:
            raise ConfinementUnavailable(f"path outside writable set: {outside}")
        return _run_local(argv, cwd, deadline)


class UnshareBackend:
    """Run argv inside a user and mount namespace. Fail closed if unshare fails."""

    name = "unshare"

    def run(
        self,
        argv: tuple[str, ...],
        cwd: Path,
        writable: tuple[Path, ...],
        readable: tuple[Path, ...],
        deadline: float,
    ) -> dict:
        del readable
        if not writable:
            raise ConfinementUnavailable("refusing to run with an empty writable set")
        config = writable[0] / ".inferrsi-confine.json"
        payload = {
            "argv": list(argv),
            "writable": [str(path) for path in writable],
            "env": dict(os.environ),
        }
        config.write_text(json.dumps(payload), encoding="utf-8")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ConfinementUnavailable("execution deadline exhausted before start")
        completed = subprocess.run(
            [
                "unshare",
                "--user",
                "--map-root-user",
                "--mount",
                "--propagation",
                "private",
                "--",
                sys.executable,
                "-c",
                "import sys; from inferrsi.infra.confinement import enter_namespace; "
                "enter_namespace(sys.argv[1])",
                str(config),
            ],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=remaining,
            check=False,
        )
        if completed.returncode != 0:
            raise ConfinementUnavailable(completed.stderr.strip() or "unshare confinement failed")
        return {
            "status": "completed",
            "returncode": 0,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }


def enter_namespace(config_path: str) -> None:
    """Remount read-only, restore writable paths, and exit before exec on failure."""
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))

    def mount(args: list[str]) -> None:
        completed = subprocess.run(["mount", *args], capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise SystemExit(completed.stderr.strip() or "mount failed")

    mount(["--make-rprivate", "/"])
    mount(["-o", "remount,bind,ro", "/"])
    for path in config["writable"]:
        mount(["-o", "bind", path, path])
        mount(["-o", "remount,bind,rw", path])
    argv = config["argv"]
    os.execvpe(argv[0], argv, config["env"])


def select_backend():
    if namespaces_available():
        return UnshareBackend()
    return UnavailableBackend()


def confined_execute(
    argv: tuple[str, ...],
    cwd: Path,
    writable_paths: tuple[Path, ...],
    readable_paths: tuple[Path, ...],
    deadline: float,
    *,
    backend=None,
) -> dict:
    """Execute argv only inside the selected boundary. Never falls back to a plain subprocess."""
    chosen = select_backend() if backend is None else backend
    writable = tuple(Path(path).resolve() for path in writable_paths)
    readable = tuple(Path(path).resolve() for path in readable_paths)
    return chosen.run(tuple(argv), Path(cwd), writable, readable, deadline)
