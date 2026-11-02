"""Filesystem confinement for candidate build and trial commands.

``execute_command`` is unchanged. The namespace backend builds a fresh root
from the writable set, the readable set and the Python runtime. It does not
remount the host root, and it does not pass the coordinator environment
through. If that view cannot be built, execution is refused. ``FixtureBackend``
is a test double: it enforces the same view with an import hook and a minimal
environment, which is not mount-namespace confinement.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_ENV_ALLOW = frozenset({"PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "PYTHONIOENCODING"})
_GUARD = """
import builtins
import os

_roots = [item for item in os.environ.get("INFERRSI_VISIBLE_ROOTS", "").split(os.pathsep) if item]
_builtin_open = builtins.open
_os_open = os.open


def _allowed(file):
    if not isinstance(file, (str, bytes, os.PathLike)):
        return True
    text = os.fsdecode(file)
    if text.startswith("<"):
        return True
    try:
        resolved = os.path.realpath(text)
    except OSError:
        return False
    return any(resolved == root or resolved.startswith(root + os.sep) for root in _roots)


def _open(file, *args, **kwargs):
    if not _allowed(file):
        raise PermissionError(file)
    return _builtin_open(file, *args, **kwargs)


def _open_fd(path, flags, mode=0o777, *, dir_fd=None):
    if dir_fd is None and not _allowed(path):
        raise PermissionError(path)
    return _os_open(path, flags, mode, dir_fd=dir_fd)


builtins.open = _open
os.open = _open_fd
"""


class ConfinementUnavailable(RuntimeError):
    """The command was not executed because confinement could not be enforced."""


def namespaces_available() -> bool:
    try:
        limit = int(Path("/proc/sys/user/max_user_namespaces").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return limit > 0


def minimal_environment(extra: dict | None = None) -> dict:
    """Coordinator credentials stay out. Only a fixed allowlist is copied."""
    environment = {key: os.environ[key] for key in _ENV_ALLOW if key in os.environ}
    if extra:
        environment.update(extra)
    return environment


def runtime_roots() -> tuple[Path, ...]:
    """Python prefix needed to start the interpreter. Never the host root."""
    candidates = [Path(sys.prefix).resolve(), Path(sys.executable).resolve().parent]
    roots: list[Path] = []
    for candidate in candidates:
        if any(candidate == earlier or earlier in candidate.parents for earlier in roots):
            continue
        roots.append(candidate)
    return tuple(roots)


def namespace_plan(
    writable: tuple[Path, ...], readable: tuple[Path, ...]
) -> dict:
    """Mount list for a fresh root. The host root itself is not an entry."""
    mounts = [{"source": str(path), "mode": "rw"} for path in writable]
    mounts.extend({"source": str(path), "mode": "ro"} for path in readable)
    covered = list(writable) + list(readable)
    for root in runtime_roots():
        if any(root == path or path in root.parents or root in path.parents for path in covered):
            continue
        mounts.append({"source": str(root), "mode": "ro"})
        covered.append(root)
    if any(item["source"] == "/" for item in mounts):
        raise ConfinementUnavailable("refusing a mount plan that exposes the host root")
    return {"mounts": mounts, "env": minimal_environment()}


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


def _run_local(argv: tuple[str, ...], cwd: Path, deadline: float, environment: dict) -> dict:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ConfinementUnavailable("execution deadline exhausted before start")
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            env=environment,
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
    """Enforce the visible roots and minimal environment. Not a mount namespace."""

    name = "fixture"

    def run(
        self,
        argv: tuple[str, ...],
        cwd: Path,
        writable: tuple[Path, ...],
        readable: tuple[Path, ...],
        deadline: float,
    ) -> dict:
        outside = _outside_writable(argv, writable)
        if outside is not None:
            raise ConfinementUnavailable(f"path outside writable set: {outside}")
        visible = tuple(dict.fromkeys(writable + readable + runtime_roots()))
        try:
            guard_dir = tempfile.mkdtemp(prefix="inferrsi-guard-")
            Path(guard_dir, "sitecustomize.py").write_text(_GUARD, encoding="utf-8")
        except OSError as exc:
            raise ConfinementUnavailable("confinement guard could not be installed") from exc
        environment = minimal_environment(
            {
                "PYTHONPATH": guard_dir,
                "INFERRSI_VISIBLE_ROOTS": os.pathsep.join(str(path) for path in visible),
            }
        )
        return _run_local(argv, cwd, deadline, environment)


class UnshareBackend:
    """Run argv in a fresh root. Fail closed if the namespace cannot be built."""

    name = "unshare"

    def run(
        self,
        argv: tuple[str, ...],
        cwd: Path,
        writable: tuple[Path, ...],
        readable: tuple[Path, ...],
        deadline: float,
    ) -> dict:
        if not writable:
            raise ConfinementUnavailable("refusing to run with an empty writable set")
        plan = namespace_plan(writable, readable)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ConfinementUnavailable("execution deadline exhausted before start")
        config_path = None
        completed = None
        try:
            handle = tempfile.NamedTemporaryFile(
                prefix="inferrsi-confine-", suffix=".json", delete=False
            )
            config_path = Path(handle.name)
            handle.close()
            config_path.write_text(
                json.dumps({"argv": list(argv), "cwd": str(cwd), **plan}),
                encoding="utf-8",
            )
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
                    str(config_path),
                ],
                cwd=cwd,
                env=minimal_environment(),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=remaining,
                check=False,
            )
        finally:
            if config_path is not None:
                config_path.unlink(missing_ok=True)
        if completed is None or completed.returncode != 0:
            detail = "unshare confinement failed"
            if completed is not None and completed.stderr.strip():
                detail = completed.stderr.strip()
            raise ConfinementUnavailable(detail)
        return {
            "status": "completed",
            "returncode": 0,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }


def enter_namespace(config_path: str) -> None:
    """Bind only the planned paths into a tmpfs root, then chroot. Exit before exec on failure."""
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    jail = Path(tempfile.mkdtemp(prefix="inferrsi-jail-"))

    def mount(args: list[str]) -> None:
        completed = subprocess.run(["mount", *args], capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise SystemExit(completed.stderr.strip() or "mount failed")

    mount(["-t", "tmpfs", "tmpfs", str(jail)])
    for item in config["mounts"]:
        source = item["source"]
        if source == "/":
            raise SystemExit("refusing to mount the host root")
        target = jail / Path(source).resolve().relative_to("/")
        target.mkdir(parents=True, exist_ok=True)
        mount(["--bind", source, str(target)])
        if item["mode"] == "ro":
            mount(["-o", "remount,bind,ro", str(target)])
    os.chroot(jail)
    os.chdir(config["cwd"])
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
