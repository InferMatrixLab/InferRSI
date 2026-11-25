"""Run public-suite tasks (Φ-Bench first) and score them with the suite's own grader.

The flow is: task package -> land a change (a reference control, a candidate
patch or one agent command) -> capture the working-tree patch with the
package's ``pre_artifacts.sh`` -> run the package's grader -> judge the
``reward.json`` it writes. Benchmark (``inferrsi.benchmark.external``) owns
the task reading and the judgment; this module owns process execution.

Two executors:

- ``docker`` delegates the whole run to the suite's ``scripts/run_task.py``,
  which builds the task image and grades in a fresh offline container. This is
  the suite's reference path.
- ``rootless`` serves hosts without Docker or user namespaces. It recreates
  the image layout under one directory and maps it onto the container paths
  with ``proot``. It replays the Dockerfile's ``COPY`` and ``ENV``
  instructions, the one-commit baseline of ``/app/repo`` and the frozen
  ``/opt/verifier-baseline`` copies; it does not run other ``RUN`` steps
  (system or Python package installs). Supply a Python environment that has
  the task's dependencies with ``python_env``. Every result records
  ``fidelity`` and the Dockerfile steps it did not replay.

In agent mode the suite's ``tests/`` and ``solution/`` are staged only after the
agent has finished, mirroring the suite's mount-for-grading-only split; named
environment variables can be forwarded into that one step with ``agent_env``.
``inferrsi_plugin`` additionally puts a built InferRSI Codex plugin in that step's tree
and tells the agent to use InferRSI (rootless only): the plugin's standard
directory-plus-prompt use, so one run differs from its control only by InferRSI.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from inferrsi.benchmark.external import phibench

MODES = (*phibench.CONTROLS, "candidate", "agent")
EXECUTORS = ("rootless", "docker")
_BASE_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
_CONTROL_FLAG = {"oracle": "", "negative": "--negative", "noop": "--noop"}


# --------------------------------------------------------------------------- Dockerfile


def _logical_lines(text: str) -> list[str]:
    """Join continuations and drop heredoc bodies, which are RUN payloads."""
    lines, current, heredoc = [], "", None
    for raw in text.splitlines():
        if heredoc is not None:
            if raw.strip() == heredoc:
                heredoc = None
            continue
        stripped = raw.strip()
        if not current and (not stripped or stripped.startswith("#")):
            continue
        if current and stripped.startswith("#"):
            continue
        current += (" " if current else "") + stripped.rstrip("\\").strip()
        if stripped.endswith("\\"):
            continue
        marker = re.search(r"<<-?\s*'?\"?([A-Za-z_][A-Za-z0-9_]*)'?\"?", current)
        if marker:
            heredoc = marker.group(1)
        lines.append(current)
        current = ""
    if current:
        lines.append(current)
    return lines


def _expand(value: str, env: dict[str, str]) -> str:
    return re.sub(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?",
                  lambda m: env.get(m.group(1), ""), value)


def parse_dockerfile(path: Path) -> dict:
    """Extract what the rootless executor can replay from a task Dockerfile."""
    env: dict[str, str] = {"PATH": _BASE_PATH}
    build_args: dict[str, str] = {}
    copies, baseline_copies, workdir, unreplayed = [], [], None, []
    for line in _logical_lines(Path(path).read_text(encoding="utf-8")):
        word, _, rest = line.partition(" ")
        word = word.upper()
        if word == "ARG":
            key, _, value = rest.strip().partition("=")
            build_args[key] = value
        elif word == "ENV":
            tokens = shlex.split(rest)
            pairs = ([tuple(t.split("=", 1)) for t in tokens] if "=" in tokens[0]
                     else [(tokens[0], " ".join(tokens[1:]))])
            for key, value in pairs:
                env[key] = _expand(value, {**build_args, **env})
        elif word == "COPY":
            tokens = [t for t in shlex.split(rest) if not t.startswith("--")]
            if any(t.startswith("--from") for t in shlex.split(rest)) or len(tokens) != 2:
                unreplayed.append(line[:160])
                continue
            copies.append((tokens[0], tokens[1]))
        elif word == "WORKDIR":
            workdir = _expand(rest.strip(), env)
        elif word == "RUN":
            found = re.findall(
                r'\bcp\s+"?(/app/[^"\s]+)"?\s+"?(/opt/verifier-baseline/[^"\s]+)"?', rest)
            baseline_copies.extend(found)
            replayed = found or "git init" in rest or re.search(r"\bvenv\b", rest) \
                or re.match(r"mkdir -p\s", rest)
            if not replayed:
                unreplayed.append(line[:160])
    env.pop("DEBIAN_FRONTEND", None)
    return {"env": env, "copies": copies, "baseline_copies": baseline_copies,
            "workdir": workdir, "unreplayed": unreplayed}


# --------------------------------------------------------------------------- staging


def _host(root: Path, container_path: str) -> Path:
    return root / container_path.lstrip("/")


def _copy(src: Path, dst: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True, symlinks=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.email=reviewer@fai-bench.local", "-c", "user.name=fai-bench",
                    "-c", "init.defaultBranch=main", "-C", str(repo), *args],
                   check=True, capture_output=True, text=True)


def stage_rootless(task: phibench.PhiTask, root: Path, *, python: str,
                   python_env: Path | None = None, include_tests: bool = True,
                   include_solution: bool = True) -> dict:
    """Recreate the task image layout under ``root``; return the replay record.

    ``include_tests``/``include_solution`` exist for agent mode: the suite keeps
    ``tests/`` and ``solution/`` out of the agent's container and mounts them only
    for grading, so the agent cannot read the hidden cases or the reference patch.
    """
    package = task.package_root
    plan = parse_dockerfile(package / "environment" / "Dockerfile")
    if root.exists():
        raise ValueError(f"Staging directory already exists: {root}")
    for path in ("app/repo", "app/.timer", "app/workspace", "logs/verifier", "logs/agent",
                 "logs/artifacts", "opt", "root", "tmp"):
        (root / path).mkdir(parents=True, exist_ok=True)
    for src, dst in plan["copies"]:
        source = (package / src).resolve()
        if package not in source.parents and source != package:
            raise ValueError(f"COPY source escapes the package: {src}")
        target = _host(root, dst)
        if source.is_dir():
            _copy(source, target)
        else:
            _copy(source, target / source.name if dst.endswith("/") else target)
    repo = root / "app" / "repo"
    if repo.is_dir() and not (repo / ".git").exists():
        with (repo / ".gitignore").open("a", encoding="utf-8") as handle:
            handle.write("__pycache__/\n*.pyc\n")
        _git(repo, "init", "-q")
        _git(repo, "config", "core.fileMode", "false")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "baseline (graded starting point)")
        shutil.rmtree(repo / ".git" / "logs", ignore_errors=True)
    for src, dst in plan["baseline_copies"]:
        _copy(_host(root, src), _host(root, dst))
    if include_tests:
        _copy(package / "tests", root / "tests")
    if include_solution and (package / "solution").is_dir():
        _copy(package / "solution", root / "solution")
    venv = plan["env"].get("VENV")
    if venv:
        target = _host(root, venv)
        if python_env is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(Path(python_env).resolve(), target_is_directory=True)
        else:
            subprocess.run([python, "-m", "venv", str(target)], check=True,
                           capture_output=True, text=True)
    return {"executor": "rootless", "fidelity": "approximate",
            "env": plan["env"], "workdir": plan["workdir"] or "/app/repo",
            "replayed_copies": [list(c) for c in plan["copies"]],
            "replayed_baseline_copies": [list(c) for c in plan["baseline_copies"]],
            "unreplayed_dockerfile_steps": plan["unreplayed"],
            "python_env": str(python_env) if python_env else f"fresh venv from {python}"}


def proot_argv(proot: str, root: Path, command: str, *, env: dict[str, str], cwd: str,
               extra_binds: list[tuple[Path, str]] = ()) -> list[str]:
    binds = [(root / name, "/" + name) for name in ("app", "opt", "logs", "tmp", "root")]
    binds.append((root / "tests", "/tests"))
    binds.extend(extra_binds)
    argv = [proot]
    for host, container in binds:
        argv += ["-b", f"{Path(host).resolve()}:{container}"]
    argv += ["-w", cwd, "/usr/bin/env", "-i"]
    argv += [f"{key}={value}" for key, value in sorted(env.items())]
    return argv + ["HOME=/root", "bash", "-c", command]


def _run(argv: list[str], log: Path, timeout: float | None) -> dict:
    started = time.monotonic()
    with log.open("w", encoding="utf-8") as handle:
        try:
            code = subprocess.run(argv, stdout=handle, stderr=subprocess.STDOUT,
                                  timeout=timeout, check=False).returncode
        except subprocess.TimeoutExpired:
            code = None
    return {"exit_code": code, "timed_out": code is None,
            "seconds": round(time.monotonic() - started, 1), "log": str(log)}


def _verifier_timeout(task: phibench.PhiTask) -> float | None:
    text = (task.package_root / "task.toml").read_text(encoding="utf-8")
    section = re.search(r"^\[verifier\](.*?)(?=^\[|\Z)", text, re.S | re.M)
    match = section and re.search(r"^timeout_sec\s*=\s*([0-9.]+)", section.group(1), re.M)
    return float(match.group(1)) if match else None


def _agent_timeout(task: phibench.PhiTask) -> float | None:
    text = (task.package_root / "task.toml").read_text(encoding="utf-8")
    section = re.search(r"^\[agent\](.*?)(?=^\[|\Z)", text, re.S | re.M)
    match = section and re.search(r"^timeout_sec\s*=\s*([0-9.]+)", section.group(1), re.M)
    return float(match.group(1)) if match else None


def _landing(task, mode, candidate_patch, agent_command, root):
    binds = []
    if mode in phibench.CONTROLS:
        if mode != "noop" and not task.has_oracle:
            return None, binds
        binds.append((root / "solution", "/solution"))
        return f"bash /solution/solve.sh {_CONTROL_FLAG[mode]}".strip(), binds
    if mode == "candidate":
        patch = Path(candidate_patch).resolve()
        binds.append((patch.parent, "/candidate"))
        return ("git -C /app/repo apply --whitespace=nowarn "
                f"/candidate/{shlex.quote(patch.name)}"), binds
    return agent_command, binds


_PLUGIN_MOUNT = "/opt/inferrsi-plugin"
_PLUGIN_NOTE = """

## InferRSI

Use InferRSI for this task. The InferRSI Codex plugin is at `{mount}`: read
`{mount}/skills/inferrsi/SKILL.md` and run InferRSI with
`python -X utf8 {mount}/skills/inferrsi/scripts/inferrsi.py <command>`.
"""


def stage_inferrsi_plugin(root: Path, plugin: Path) -> dict:
    """Put a built InferRSI Codex plugin in the agent's tree and say to use InferRSI.

    This is the plugin's standard use without a client that can import its archive:
    the plugin directory plus a prompt naming it. Retrieval and skill selection stay
    with the agent. Returns the record of the staged plugin and the original
    instruction for restoring before grading.
    """
    plugin = Path(plugin).resolve()
    launcher = plugin / "skills" / "inferrsi" / "scripts" / "inferrsi.py"
    manifest = plugin / "runtime" / "manifest.json"
    for required in (plugin / "plugin.json", plugin / "skills" / "inferrsi" / "SKILL.md",
                     launcher, manifest):
        if not required.is_file():
            raise ValueError(f"Not a built InferRSI Codex plugin (missing {required}); "
                             "build one with tools/build_codex_plugin.py")
    _copy(plugin, _host(root, _PLUGIN_MOUNT))
    instruction_path = root / "app" / "instruction.md"
    instruction = instruction_path.read_text(encoding="utf-8")
    instruction_path.write_text(instruction + _PLUGIN_NOTE.format(mount=_PLUGIN_MOUNT),
                                encoding="utf-8")
    runtime = json.loads(manifest.read_text(encoding="utf-8"))
    return {"usage": "plugin directory + prompt", "plugin": str(plugin),
            "mount": _PLUGIN_MOUNT,
            "plugin_version": json.loads((plugin / "plugin.json").read_text(
                encoding="utf-8")).get("version"),
            "runtime_version": runtime.get("runtime_version"),
            "content_sha256": runtime.get("content_sha256"),
            "note": _PLUGIN_NOTE.format(mount=_PLUGIN_MOUNT).strip(),
            "original_instruction": instruction}


def run_rootless(task: phibench.PhiTask, mode: str, out: Path, *, proot: str, python: str,
                 python_env: Path | None = None, candidate_patch: Path | None = None,
                 agent_command: str | None = None,
                 agent_env: dict[str, str] | None = None,
                 inferrsi_plugin: Path | None = None) -> dict:
    root = out / "root"
    # The suite does not put tests/ or solution/ in the agent's container: they are
    # mounted only for grading. Keep that split here, or an agent could read the
    # hidden cases and the reference patch before it edits anything.
    agent_step = mode == "agent"
    record = stage_rootless(task, root, python=python, python_env=python_env,
                            include_tests=not agent_step, include_solution=not agent_step)
    record["grading_assets_exposed_to_agent"] = not agent_step
    original_instruction = None
    if inferrsi_plugin is not None:
        staged = stage_inferrsi_plugin(root, inferrsi_plugin)
        original_instruction = staged.pop("original_instruction")
        record["inferrsi"] = staged
    env = dict(record.pop("env"))
    workdir = record.pop("workdir")
    landing, binds = _landing(task, mode, candidate_patch, agent_command, root)
    if landing is None:
        record.update(status="skipped", reason="task ships no reference landing for this control")
        return record
    stage_env = {**env, "PHI_TASK": task.task_id, "PHI_INSTRUCTION": "/app/instruction.md"}
    # proot passes its environment as argv, so a value put there is visible in `ps` on a
    # shared host. Hand the agent step a mode-600 file inside its own root instead and
    # remove it once the step is over.
    env_file = root / "root" / ".phi-agent-env"
    if agent_env:
        env_file.write_text("".join(f"{name}={shlex.quote(value)}\n"
                                    for name, value in sorted(agent_env.items())),
                            encoding="utf-8")
        env_file.chmod(0o600)
        landing = "set -a; . /root/.phi-agent-env; set +a; " + landing
    record["landing"] = {"command": landing, **_run(
        proot_argv(proot, root, landing, env=stage_env, cwd=workdir, extra_binds=binds),
        out / "landing.log", _agent_timeout(task) if agent_step else None)}
    if env_file.exists():
        env_file.unlink()
    if original_instruction is not None:
        # Hand the grader the task's own statement, as without the InferRSI note.
        (root / "app" / "instruction.md").write_text(original_instruction, encoding="utf-8")
    capture_binds = [(task.package_root / "pre_artifacts.sh", "/phi/pre_artifacts.sh")]
    record["capture"] = _run(
        proot_argv(proot, root, "bash /phi/pre_artifacts.sh", env=env, cwd=workdir,
                   extra_binds=capture_binds),
        out / "capture.log", None)
    if agent_step:
        _copy(task.package_root / "tests", root / "tests")
    record["grade"] = _run(proot_argv(proot, root, "bash /tests/test.sh", env=env, cwd=workdir),
                           out / "verify.log", _verifier_timeout(task))
    record["artifacts"] = str(root / "logs" / "artifacts")
    record["verifier_dir"] = str(root / "logs" / "verifier")
    record["status"] = "graded" if record["landing"]["exit_code"] == 0 else "landing_failed"
    return record


def docker_argv(task: phibench.PhiTask, mode: str, out: Path, *, python: str,
                runner_args: list[str] = ()) -> list[str]:
    if mode not in phibench.CONTROLS:
        raise ValueError("The docker executor runs reference controls only; score candidates "
                         "with the suite runner's own --agent options via runner arguments")
    return [python, str(task.suite_root / "scripts" / "run_task.py"), "--task", task.task_id,
            "--agent", "oracle", "--oracle-variant", mode, "--runs-dir", str(out),
            "--run-name", f"{task.name}-{mode}", *runner_args]


def run_docker(task: phibench.PhiTask, mode: str, out: Path, *, python: str,
               runner_args: list[str] = ()) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    record = {"executor": "docker", "fidelity": "suite-reference",
              "grade": _run(docker_argv(task, mode, out, python=python, runner_args=runner_args),
                            out / "runner.log", None)}
    run_dir = out / f"{task.name}-{mode}"
    record["verifier_dir"] = str(run_dir / "verifier")
    record["artifacts"] = str(run_dir / "artifacts")
    run_json = run_dir / "run.json"
    if run_json.is_file():
        runner = json.loads(run_json.read_text(encoding="utf-8"))
        record["runner_status"] = runner.get("status")
        if runner.get("status") == "skipped":
            record.update(status="skipped", reason=runner.get("skip_reason"))
            return record
    record["status"] = "graded"
    return record


# --------------------------------------------------------------------------- entry points


def run_mode(task: phibench.PhiTask, mode: str, out: Path, *, executor: str,
             proot: str | None = None, python: str | None = None,
             python_env: Path | None = None, candidate_patch: Path | None = None,
             agent_command: str | None = None, agent_env: dict[str, str] | None = None,
             inferrsi_plugin: Path | None = None, runner_args: list[str] = ()) -> dict:
    if mode not in MODES:
        raise ValueError(f"Unknown mode: {mode}")
    if executor not in EXECUTORS:
        raise ValueError(f"Unknown executor: {executor}")
    if (mode == "candidate") != (candidate_patch is not None):
        raise ValueError("--candidate-patch is required for, and only for, mode candidate")
    if (mode == "agent") != bool(agent_command):
        raise ValueError("--agent-command is required for, and only for, mode agent")
    if mode != "agent" and agent_env:
        raise ValueError("--agent-env is only for mode agent")
    if inferrsi_plugin is not None and (mode != "agent" or executor != "rootless"):
        raise ValueError("--inferrsi-plugin is only for mode agent with the rootless executor")
    python = python or sys.executable
    out = Path(out) / mode
    if out.exists():
        raise ValueError(f"Output directory already exists: {out}")
    out.mkdir(parents=True)
    if executor == "docker":
        record = run_docker(task, mode, out, python=python, runner_args=list(runner_args))
    else:
        if not proot or not shutil.which(proot):
            raise ValueError("The rootless executor needs a proot binary (--proot)")
        record = run_rootless(task, mode, out, proot=proot, python=python, python_env=python_env,
                              candidate_patch=candidate_patch, agent_command=agent_command,
                              agent_env=agent_env, inferrsi_plugin=inferrsi_plugin)
    record = {"suite": phibench.SUITE, "task": task.describe(), "mode": mode, **record}
    if record.get("status") == "graded":
        record["score"] = phibench.read_reward(Path(record["verifier_dir"]))
        patch = Path(record["artifacts"]) / "model.patch"
        record["model_patch_bytes"] = patch.stat().st_size if patch.is_file() else None
    (out / "result.json").write_text(json.dumps(record, indent=2, ensure_ascii=False),
                                     encoding="utf-8")
    return record


def selfcheck(task: phibench.PhiTask, out: Path, *, oracle_tolerance: float | None,
              **options) -> dict:
    """Run noop, negative and oracle, then judge them with the suite's expectations."""
    results = {control: run_mode(task, control, out, **options)
               for control in phibench.CONTROLS}
    assessment = phibench.assess_controls(
        task, {control: result.get("score") for control, result in results.items()},
        oracle_tolerance=oracle_tolerance)
    assessment["runs"] = {
        control: {"status": result.get("status"), "score": result.get("score"),
                  "result": str(Path(out) / control / "result.json")}
        for control, result in results.items()}
    executor = options.get("executor")
    assessment["executor"] = executor
    if executor == "rootless":
        assessment["fidelity_note"] = ("rootless replay of the task image; Dockerfile steps it "
                                       "did not run are listed in each result.json")
    Path(out, "selfcheck.json").write_text(json.dumps(assessment, indent=2, ensure_ascii=False),
                                           encoding="utf-8")
    return assessment


def list_command(root: Path) -> list[dict]:
    return [task.describe() for task in phibench.list_tasks(root)]


def command(args) -> tuple[dict | list, int]:
    """CLI adapter: returns (printable result, exit status)."""
    root = Path(args.root)
    if args.external_action == "list":
        return list_command(root), 0
    task = phibench.get_task(root, args.task)
    options = {"executor": args.executor, "proot": args.proot, "python": args.python,
               "python_env": args.python_env, "runner_args": args.runner_arg or []}
    agent_env = {}
    for name in getattr(args, "agent_env", None) or []:
        if name not in os.environ:
            raise ValueError(f"--agent-env {name}: not set in this process")
        agent_env[name] = os.environ[name]
    if args.external_action == "selfcheck":
        result = selfcheck(task, Path(args.output), oracle_tolerance=args.oracle_tolerance,
                           **options)
        return result, 0 if result["verdict"] == "PASS" else 1
    result = run_mode(task, args.mode, Path(args.output), candidate_patch=args.candidate_patch,
                      agent_command=args.agent_command, agent_env=agent_env,
                      inferrsi_plugin=getattr(args, "inferrsi_plugin", None), **options)
    return result, 0 if result.get("status") == "graded" else 1


__all__ = ["EXECUTORS", "MODES", "command", "docker_argv", "list_command", "parse_dockerfile",
           "proot_argv", "run_mode", "selfcheck", "stage_inferrsi_plugin", "stage_rootless"]
