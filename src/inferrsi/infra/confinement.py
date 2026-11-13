"""Filesystem confinement for candidate build and trial commands.

``execute_command`` is unchanged. The namespace backend builds a fresh root
from the writable set, the readable set and the Python runtime. It does not
remount the host root, and it does not pass the coordinator environment
through. If that view cannot be built, execution is refused. ``FixtureBackend``
is a test double: it enforces the same view with an import hook and a minimal
environment, which is not mount-namespace confinement.

Callers may add device nodes (bound read-write, e.g. one GPU's ``/dev/nvidiaN``),
extra read-only runtime paths (e.g. the driver's user-space libraries) and extra
environment variables. Every command runs as PID 1 of its own PID namespace, so
when it exits or is killed nothing it started survives. With device nodes, the
jail also gets a fresh ``/proc``; the host ``/proc`` is never bound. Every jail
has an empty ``/tmp`` and ``/dev/shm``.
"""

import json
import os
import signal
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_ENV_ALLOW = frozenset({"PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "PYTHONIOENCODING"})
_PACKAGE_ROOT = str(Path(__file__).resolve().parents[2])
_SUPERVISOR = (
    "import sys; sys.path.insert(0, sys.argv[1]); "
    "from inferrsi.infra.confinement import enter_namespace; enter_namespace(sys.argv[2])"
)
_REAP_SECONDS = 10.0
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
    """True only when a user namespace can actually be created.

    A positive ``max_user_namespaces`` is not enough: unprivileged ``unshare``
    can still return EPERM. Callers that skip live tests must see that as
    unavailable instead of starting a command that errors.
    """
    try:
        limit = int(Path("/proc/sys/user/max_user_namespaces").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if limit <= 0:
        return False
    try:
        probe = subprocess.run(
            ["unshare", "--user", "--map-root-user", "--mount", "--", "true"],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


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


def _elf_interpreter(executable: Path) -> str | None:
    """PT_INTERP path recorded in the executable, or None for a static binary."""
    data = executable.read_bytes()
    if data[:4] != b"\x7fELF":
        return None
    endian = "<" if data[5] == 1 else ">"
    if data[4] == 2:
        phoff = struct.unpack_from(endian + "Q", data, 32)[0]
        phentsize, phnum = struct.unpack_from(endian + "HH", data, 54)
        header = endian + "IIQQQQ"
    elif data[4] == 1:
        phoff = struct.unpack_from(endian + "I", data, 28)[0]
        phentsize, phnum = struct.unpack_from(endian + "HH", data, 42)
        header = endian + "IIIIIIII"
    else:
        raise ConfinementUnavailable("unsupported ELF class")
    for index in range(phnum):
        start = phoff + index * phentsize
        fields = struct.unpack_from(header, data, start)
        if fields[0] != 3:
            continue
        offset, size = (fields[2], fields[5]) if data[4] == 2 else (fields[1], fields[4])
        return data[offset : offset + size].split(b"\0", 1)[0].decode()
    return None


def _shared_libraries(executable: Path) -> tuple[str, ...]:
    """Absolute libraries ldd resolves. The virtual dynamic linker object is skipped."""
    completed = subprocess.run(
        ["ldd", os.fspath(executable)], capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise ConfinementUnavailable(completed.stderr.strip() or "ldd failed")
    found: list[str] = []
    for line in completed.stdout.splitlines():
        if "=>" in line:
            token = line.split("=>", 1)[1].strip().split()[0]
        else:
            token = line.strip().split()[0]
        if token.startswith("/"):
            found.append(token)
    return tuple(found)


def runtime_files() -> tuple[Path, ...]:
    """Loader and shared libraries that live outside the Python prefix."""
    executable = Path(sys.executable)
    names: list[Path] = []
    interpreter = _elf_interpreter(executable)
    if interpreter:
        names.append(Path(interpreter))
    elif executable.read_bytes()[:4] == b"\x7fELF":
        return ()
    for item in _shared_libraries(executable):
        names.append(Path(item))
    cache = Path("/etc/ld.so.cache")
    if cache.is_file():
        names.append(cache)
    unique: list[Path] = []
    for path in names:
        if path not in unique:
            unique.append(path)
    return tuple(unique)


def _covered(path: Path, covered: list[Path]) -> bool:
    return any(path == root or root in path.parents for root in covered)


def namespace_plan(
    writable: tuple[Path, ...],
    readable: tuple[Path, ...],
    devices: tuple[Path, ...] = (),
    runtime: tuple[Path, ...] = (),
    env: dict | None = None,
) -> dict:
    """Mount list for a fresh root. The host root itself is not an entry."""
    mounts: list[dict] = []
    covered: list[Path] = []

    def add(path: Path, mode: str, *, directory: bool) -> None:
        source = str(path)
        if source == "/" or ".." in path.parts:
            raise ConfinementUnavailable("refusing a mount plan that exposes the host root")
        if any(item["source"] == source for item in mounts) or _covered(path, covered):
            return
        mounts.append({"source": source, "mode": mode})
        if directory:
            covered.append(path)

    for path in writable:
        add(path, "rw", directory=True)
    for path in devices:
        add(path, "dev", directory=False)
    for path in readable:
        add(path, "ro", directory=True)
    for path in runtime:
        add(path, "ro", directory=path.is_dir())
    for root in runtime_roots():
        add(root, "ro", directory=True)
    for extra in runtime_files():
        add(extra, "ro", directory=False)
    return {"mounts": mounts, "env": minimal_environment(env), "proc": bool(devices)}


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


def supervisor_command(config_path: Path) -> list[str]:
    """Isolated interpreter: the candidate cwd and PYTHON* variables do not reach sys.path."""
    return [sys.executable, "-I", "-c", _SUPERVISOR, _PACKAGE_ROOT, str(config_path)]


def _kill_group(process: subprocess.Popen) -> None:
    """Kill the session and return only once no member of it is left."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()
    for stream in (process.stdout, process.stderr):
        if stream is not None:
            stream.close()
    give_up = time.monotonic() + _REAP_SECONDS
    while True:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        if time.monotonic() > give_up:
            raise ConfinementUnavailable("namespace command outlived its deadline")
        time.sleep(0.05)


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
        **extras,
    ) -> dict:
        del argv, cwd, writable, readable, deadline, extras
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
        *,
        devices: tuple[Path, ...] = (),
        runtime: tuple[Path, ...] = (),
        env: dict | None = None,
    ) -> dict:
        outside = _outside_writable(argv, writable)
        if outside is not None:
            raise ConfinementUnavailable(f"path outside writable set: {outside}")
        visible = tuple(dict.fromkeys(writable + devices + readable + runtime + runtime_roots()))
        try:
            guard_dir = tempfile.mkdtemp(prefix="inferrsi-guard-")
            Path(guard_dir, "sitecustomize.py").write_text(_GUARD, encoding="utf-8")
        except OSError as exc:
            raise ConfinementUnavailable("confinement guard could not be installed") from exc
        environment = minimal_environment(
            {
                **(env or {}),
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
        *,
        devices: tuple[Path, ...] = (),
        runtime: tuple[Path, ...] = (),
        env: dict | None = None,
    ) -> dict:
        if not writable:
            raise ConfinementUnavailable("refusing to run with an empty writable set")
        plan = namespace_plan(writable, readable, devices, runtime, env)
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
            process = subprocess.Popen(
                [
                    "unshare",
                    "--user",
                    "--map-root-user",
                    "--mount",
                    "--propagation",
                    "private",
                    "--pid",
                    "--kill-child",
                    "--",
                    *supervisor_command(config_path),
                ],
                cwd=cwd,
                env=minimal_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            try:
                stdout, stderr = process.communicate(timeout=remaining)
            except subprocess.TimeoutExpired as exc:
                _kill_group(process)
                raise ConfinementUnavailable("namespace command timed out") from exc
            completed = subprocess.CompletedProcess(
                process.args, process.returncode, stdout, stderr
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
        source_path = Path(source)
        if source == "/" or not source_path.is_absolute() or ".." in source_path.parts:
            raise SystemExit("refusing to mount the host root")
        target = jail.joinpath(*source_path.parts[1:])
        if source_path.is_dir() and not source_path.is_symlink():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()
        mount(["--bind", source, str(target)])
        if item["mode"] == "ro":
            mount(["-o", "remount,bind,ro", str(target)])
    bound = {item["source"] for item in config["mounts"]}
    for scratch in ("/tmp", "/dev/shm"):
        if scratch in bound:
            continue
        target = jail.joinpath(*Path(scratch).parts[1:])
        target.mkdir(parents=True, exist_ok=True)
        target.chmod(0o1777)
    if config.get("proc"):
        (jail / "proc").mkdir(exist_ok=True)
        mount(["-t", "proc", "proc", str(jail / "proc")])
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
    device_paths: tuple[Path, ...] = (),
    runtime_paths: tuple[Path, ...] = (),
    env: dict | None = None,
) -> dict:
    """Execute argv only inside the selected boundary. Never falls back to a plain subprocess."""
    chosen = select_backend() if backend is None else backend
    writable = tuple(Path(path).resolve() for path in writable_paths)
    readable = tuple(Path(path).resolve() for path in readable_paths)
    return chosen.run(
        tuple(argv),
        Path(cwd),
        writable,
        readable,
        deadline,
        devices=tuple(Path(path) for path in device_paths),
        runtime=tuple(Path(path) for path in runtime_paths),
        env=env,
    )
