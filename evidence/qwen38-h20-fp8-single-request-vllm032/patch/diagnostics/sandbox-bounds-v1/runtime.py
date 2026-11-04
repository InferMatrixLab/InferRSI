"""Resolve pinned EvalPlus metadata, inventory readonly binds and run a trusted probe."""

import argparse
import configparser
import hashlib
import importlib.metadata
import json
import os
import re
import resource
import shutil
import signal
import subprocess
import sys
import sysconfig
import threading
import tomllib
from pathlib import Path

REVISION = "26d6d00bb1fd0fa37f39c99d5290da67891d1c5e"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    with path.open("xb") as stream:
        stream.write(canonical(value) + b"\n")


def git(source, *args):
    return subprocess.check_output(["git", "-C", str(source), *args])


def source_identity(bundle):
    source = bundle / "source"
    if git(source, "rev-parse", "HEAD").decode().strip() != REVISION:
        raise ValueError("wrong EvalPlus source revision")
    if git(source, "diff", "HEAD", "--"):
        raise ValueError("tracked EvalPlus source changed")
    return {
        "evaluator_revision": REVISION,
        "archive_sha256": sha(git(source, "archive", "--format=tar", "HEAD")),
    }


def requirements(bundle):
    identity = source_identity(bundle)
    config = configparser.ConfigParser()
    config.read(bundle / "source/setup.cfg")
    dependencies = [
        line.strip() for line in config["options"]["install_requires"].splitlines() if line.strip()
    ]
    build = tomllib.loads((bundle / "source/pyproject.toml").read_text())["build-system"][
        "requires"
    ]
    (bundle / "dependencies.in").write_text("\n".join(dependencies) + "\n")
    (bundle / "build.in").write_text("\n".join([*build, "wheel"]) + "\n")
    write(
        bundle / "source.json",
        {
            **identity,
            "official_default_dependencies": dependencies,
            "build_dependencies": [*build, "wheel"],
            "extras_enabled": [],
            "generated_code_executed": False,
        },
    )


def verify_source(bundle):
    expected = json.loads((bundle / "source.json").read_bytes())
    if any(
        source_identity(bundle)[name] != expected[name]
        for name in ("evaluator_revision", "archive_sha256")
    ):
        raise ValueError("EvalPlus source snapshot drift")


def tree(root, alias):
    result = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        name = alias + "/" + relative
        if path.is_symlink():
            target = os.readlink(path)
            if Path(target).is_absolute() or not path.resolve(strict=True).is_relative_to(root):
                raise ValueError("runtime symlink escapes its readonly root")
            result.append({"path": name, "type": "symlink", "target": target})
        elif path.is_dir():
            result.append({"path": name, "type": "directory", "mode": path.stat().st_mode & 0o777})
        elif path.is_file():
            result.append(
                {
                    "path": name,
                    "type": "file",
                    "mode": path.stat().st_mode & 0o777,
                    "bytes": path.stat().st_size,
                    "sha256": sha(path.read_bytes()),
                }
            )
        else:
            raise ValueError("unsupported runtime filesystem entry")
    return result


def system_dependencies(roots):
    # Mirror the explicit relocated loader directory; inherit no host loader state.
    loader_env = {
        "PATH": "/usr/bin:/bin", "LC_ALL": "C",
        "LD_LIBRARY_PATH": str(roots[0] / "lib"),
    }
    ldd = shutil.which("ldd")
    if ldd is None:
        raise ValueError("system ELF dependency scanner unavailable")
    dependencies = {}
    for root in roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            with path.open("rb") as stream:
                if stream.read(4) != b"\x7fELF":
                    continue
            result = subprocess.run(
                [ldd, str(path)], capture_output=True, timeout=10, check=False, env=loader_env
            )
            output = result.stdout.decode(errors="replace")
            if result.returncode != 0 or "not found" in output:
                raise ValueError("ELF runtime dependency missing")
            for line in output.splitlines():
                match = re.search(r"(?:=>\s*)?(/[^\s]+)", line)
                if not match:
                    continue
                original = Path(match.group(1))
                resolved = original.resolve(strict=True)
                if any(resolved.is_relative_to(bound) for bound in roots):
                    continue
                if not str(original).startswith(("/lib/", "/lib64/", "/usr/lib/", "/usr/lib64/")):
                    raise ValueError("unexpected external runtime library")
                dependencies[str(original)] = str(resolved)
    return dependencies


def inventory(bundle, output):
    verify_source(bundle)
    task_root = Path(os.environ["TASK_ROOT"]).resolve(strict=True)
    base = Path(sys.base_prefix).resolve(strict=True)
    site = Path(sysconfig.get_path("purelib")).resolve(strict=True)
    if not base.is_relative_to(task_root) or not site.is_relative_to(task_root):
        raise ValueError("runtime roots must remain inside TASK_ROOT")
    executable = Path(sys._base_executable).resolve(strict=True).relative_to(base).as_posix()
    bwrap = shutil.which("bwrap")
    if bwrap is None:
        raise ValueError("bubblewrap is unavailable on this compute node")
    help_text = subprocess.check_output([bwrap, "--help"], stderr=subprocess.STDOUT).decode()
    for flag in (
        "--unshare-user",
        "--unshare-net",
        "--unshare-pid",
        "--disable-userns",
        "--assert-userns-disabled",
        "--clearenv",
        "--remount-ro",
        "--size",
    ):
        if flag not in help_text:
            raise ValueError("required bubblewrap isolation option unavailable")
    dependencies = system_dependencies((base, site))
    entries = tree(base, "/opt/python") + tree(site, "/opt/site-packages")
    for destination, source in dependencies.items():
        path = Path(source)
        entries.append(
            {
                "path": destination,
                "type": "file",
                "bytes": path.stat().st_size,
                "sha256": sha(path.read_bytes()),
            }
        )
    probe = Path(__file__).with_name("synthetic_probe.py")
    entries.append(
        {
            "path": "/opt/probe.py",
            "type": "file",
            "bytes": probe.stat().st_size,
            "sha256": sha(probe.read_bytes()),
        }
    )
    entries.sort(key=lambda row: row["path"])
    # Bind-set identity describes actual readonly bytes, not an OCI image.
    rootfs_digest = "sha256:" + sha(canonical(entries))
    packages = sorted(
        [
            {"name": d.metadata["Name"], "version": d.version}
            for d in importlib.metadata.distributions()
        ],
        key=lambda row: row["name"].lower(),
    )
    # Match every pinned evaluator Python source byte to the installed package.
    checked = 0
    source = bundle / "source"
    for encoded in git(source, "ls-files", "-z", "evalplus").split(b"\0"):
        if not encoded or not encoded.endswith(b".py"):
            continue
        name = encoded.decode()
        if (source / name).read_bytes() != (site / name).read_bytes():
            raise ValueError("installed EvalPlus differs from pinned source")
        checked += 1
    if checked == 0:
        raise ValueError("no pinned evaluator Python sources verified")
    output.mkdir(parents=True, exist_ok=False)
    write(
        output / "rootfs.json",
        {
            "schema": 1,
            "rootfs_kind": "readonly-bind-set-v1",
            "loader_policy": {
                "scanner_inherits_environment": False,
                "base_library_directory": "/opt/python/lib",
                "sandbox_ld_library_path": "/opt/python/lib",
            },
            "rootfs_digest": rootfs_digest,
            "evaluator_revision": REVISION,
            "entries": entries,
            "python": sys.version.split()[0],
            "packages": packages,
            "checked_evaluator_sources": checked,
            "executor": {
                "kind": "bubblewrap",
                "binary_sha256": sha(Path(bwrap).read_bytes()),
                "version": subprocess.check_output([bwrap, "--version"]).decode().strip(),
            },
            "generated_code_executed": False,
            "qualified_generated_code_executor": False,
        },
    )
    write(
        output / "runtime-locators.private.json",
        {
            "python_root": str(base),
            "site_root": str(site),
            "python_relative": executable,
            "bwrap": bwrap,
            "system_libraries": dependencies,
        },
    )


def command(locators, probe, namespaces, sentinel):
    args = [
        locators["bwrap"],
        "--unshare-user",
        "--uid",
        "65534",
        "--gid",
        "65534",
        "--unshare-net",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--hostname",
        "sandbox",
        "--disable-userns",
        "--assert-userns-disabled",
        "--cap-drop",
        "ALL",
        "--die-with-parent",
        "--new-session",
        "--clearenv",
        "--ro-bind",
        locators["python_root"],
        "/opt/python",
        "--ro-bind",
        locators["site_root"],
        "/opt/site-packages",
        "--ro-bind",
        str(probe),
        "/opt/probe.py",
    ]
    for destination, source in sorted(locators["system_libraries"].items()):
        args.extend(["--ro-bind", source, destination])
    args += [
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--size",
        "33554432",
        "--tmpfs",
        "/dev/shm",
        "--size",
        "67108864",
        "--tmpfs",
        "/work",
        "--dir",
        "/work/tmp",
        "--dir",
        "/work/output",
        "--chdir",
        "/work",
        "--remount-ro",
        "/",
    ]
    environment = {
        "HOME": "/work",
        "TMPDIR": "/work/tmp",
        "PATH": "/opt/python/bin",
        "LD_LIBRARY_PATH": "/opt/python/lib",
        "PYTHONDONTWRITEBYTECODE": "1",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "LC_ALL": "C.UTF-8",
        "PROBE_PARENT_NAMESPACES": json.dumps(namespaces),
        "PROBE_UNMOUNTED_SENTINEL": str(sentinel),
    }
    for name, value in environment.items():
        args += ["--setenv", name, value]
    return args + ["/opt/python/" + locators["python_relative"], "-I", "/opt/probe.py"]


def limits():
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    for name, value in (
        ("AS", 2147483648),
        ("CPU", 30),
        ("NOFILE", 64),
        ("FSIZE", 1048576),
        ("CORE", 0),
    ):
        resource.setrlimit(getattr(resource, "RLIMIT_" + name), (value, value))


def probe(inventory_path, output):
    rootfs = json.loads((inventory_path / "rootfs.json").read_bytes())
    locators = json.loads((inventory_path / "runtime-locators.private.json").read_bytes())
    if sha(Path(locators["bwrap"]).read_bytes()) != rootfs["executor"]["binary_sha256"]:
        raise ValueError("bubblewrap binary changed after inventory")
    output.mkdir(parents=True, exist_ok=False)
    sentinel = output / "unmounted-sentinel.private"
    sentinel.write_text("synthetic host marker, not a credential")
    namespaces = {
        name: os.readlink("/proc/self/ns/" + name) for name in ("user", "net", "pid", "uts", "ipc")
    }
    args = command(locators, Path(__file__).with_name("synthetic_probe.py"), namespaces, sentinel)
    timed_out = False
    # Sample from the supervisor after Popen. The evaluator process remains free
    # of an added observer thread before its own default multiprocessing fork.
    import psutil
    sampled = {"processes": 0, "threads": 0, "sum_vms_bytes": 0,
               "sum_rss_bytes": 0, "sum_fds": 0, "samples": 0, "errors": 0}
    known = {}
    sampling_failures = []
    stop_sampling = threading.Event()
    def observe(pid):
        try:
            parent = psutil.Process(pid)
        except psutil.NoSuchProcess:
            sampling_failures.append("launcher exited before sampling")
            return
        while not stop_sampling.is_set():
            totals = {"processes": 0, "threads": 0, "sum_vms_bytes": 0,
                      "sum_rss_bytes": 0, "sum_fds": 0}
            try:
                processes = [parent, *parent.children(recursive=True)]
            except psutil.NoSuchProcess:
                break
            except psutil.AccessDenied:
                sampling_failures.append("cannot inspect owned launcher descendants")
                return
            for child in processes:
                try:
                    known[child.pid] = child.create_time()
                    memory = child.memory_info()
                    totals["processes"] += 1
                    totals["threads"] += child.num_threads()
                    totals["sum_vms_bytes"] += memory.vms
                    totals["sum_rss_bytes"] += memory.rss
                    totals["sum_fds"] += child.num_fds()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    sampled["errors"] += 1
            for name, value in totals.items():
                sampled[name] = max(sampled[name], value)
            sampled["samples"] += 1
            stop_sampling.wait(0.01)
    with (
        (output / "stdout.json").open("xb") as stdout,
        (output / "stderr.private.log").open("xb") as stderr,
    ):
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "_exec", json.dumps(args)],
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
            env={**os.environ, "PROBE_INHERITED_SECRET": "synthetic-must-be-cleared"},
        )
        observer = threading.Thread(target=observe, args=(process.pid,), daemon=True)
        observer.start()
        try:
            code = process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.getpgid(process.pid) != process.pid:
                raise RuntimeError("owned sandbox process group changed unexpectedly")
            os.killpg(process.pid, signal.SIGKILL)
            code = process.wait(timeout=10)
        finally:
            stop_sampling.set()
            observer.join(timeout=2)
    remaining = []
    for pid, created in known.items():
        try:
            child = psutil.Process(pid)
            if child.create_time() == created and child.status() != psutil.STATUS_ZOMBIE:
                remaining.append(pid)
        except psutil.NoSuchProcess:
            pass
    result = {
        "sampled_peaks": sampled,
        "sampling_thread_joined": not observer.is_alive(),
        "sampling_failures": sampling_failures,
        "known_live_descendants_after_exit": remaining,
        "sampling_limitation": "Polling may miss transient processes; sampled peaks are not hard bounds or exhaustive cleanup proof.",
        "phase": "trusted_synthetic_evaluator",
        "exit_code": code,
        "timed_out": timed_out,
        "rootfs_digest": rootfs["rootfs_digest"],
        "executor": rootfs["executor"],
        "policy_script_sha256": sha(Path(__file__).read_bytes()),
        "probe_script_sha256": sha(Path(__file__).with_name("synthetic_probe.py").read_bytes()),
        "stdout_sha256": sha((output / "stdout.json").read_bytes()),
        "generated_code_executed": False,
        "full_evaluator_attempt_requested": True,
        "qualified_generated_code_executor": False,
        "verdict": "INCONCLUSIVE",
    }
    write(output / "execution.json", result)
    if code != 0 or timed_out or remaining or observer.is_alive() or sampling_failures or not sampled["samples"]:
        raise ValueError("trusted synthetic evaluator probe failed; retain evidence without fallback")
    payload = json.loads((output / "stdout.json").read_bytes())
    if payload.get("passed") is not True:
        raise ValueError("trusted synthetic evaluator assertions failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("requirements", "verify-source", "inventory", "probe"))
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--inventory", type=Path)
    args = parser.parse_args()
    if not os.environ.get("SLURM_JOB_ID") or os.environ.get("SLURM_GPUS_ON_NODE", "0") != "0":
        raise ValueError("CPU-only Slurm allocation required")
    if args.phase == "requirements":
        requirements(args.bundle)
    elif args.phase == "verify-source":
        verify_source(args.bundle)
    elif args.phase == "inventory":
        inventory(args.bundle, args.output)
    else:
        probe(args.inventory, args.output)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "_exec":
        # A fresh interpreter sets limits before exec; no Python preexec callback
        # runs between fork and exec in the monitoring supervisor.
        if not os.environ.get("SLURM_JOB_ID") or os.environ.get("SLURM_GPUS_ON_NODE", "0") != "0":
            raise ValueError("CPU-only Slurm allocation required")
        command_args = json.loads(sys.argv[2])
        if not command_args or any(not isinstance(value, str) for value in command_args):
            raise ValueError("invalid internal command")
        limits()
        os.execv(command_args[0], command_args)
    else:
        main()
