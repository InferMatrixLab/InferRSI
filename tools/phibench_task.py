#!/usr/bin/env python3
"""Run one Φ-Bench task with both arms and write a resumable summary.

This is the per-task worker used by ``phibench_ab.py``; it runs the same steps as
the working host script: probe -> calibrate x3 -> selfcheck -> control -> InferRSI.
Every step gets its own hard-link copy of the task venv, so one arm cannot leak
installed packages into the other. Steps already in ``summary.json`` are reused,
which is what makes ``--resume`` work.

usage:
  phibench_task.py --root phibench --runs runs --task kfc/<name> --venv /path/venv \
      --plugin /path/codex-plugin --run-id ID --plan-sha SHA [--taskenv taskenv.json]
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

# 来源：沿用工作脚本 run-one.py，probe/grade 步骤在 verifier 超时外加 600 秒。
STEP_MARGIN = 600.0


def atomic_write(path: Path, text: str) -> None:
    """Write via a sibling temp file and os.replace, so a killed run leaves the old file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def task_entry(root: Path, task: str) -> dict:
    index = read_json(root / "tasks_index.json")
    if not isinstance(index, dict) or not isinstance(index.get("tasks"), list):
        raise SystemExit(f"not a Φ-Bench clone (missing tasks_index.json): {root}")
    for entry in index["tasks"]:
        if f"{entry.get('bench')}/{entry.get('task')}" == task:
            return entry
    raise SystemExit(f"unknown task: {task}")


def toml_timeout(root: Path, entry: dict, section: str, default: float) -> float:
    path = root / entry["package_root"] / "task.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    table = data.get(section)
    value = table.get("timeout_sec") if isinstance(table, dict) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        value = data.get("timeout_sec")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return default
    return float(value)


def venv_copy(venv: Path, scratch: Path, deepcopy: list[str]) -> Path:
    """A private hard-link copy of the task venv, like the host script makes per step."""
    target = scratch / f"venv-{time.time_ns()}"
    scratch.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["cp", "-al", str(venv), str(target)], check=True,
                       capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError):
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(venv, target, symlinks=True)
    for rel in deepcopy:
        shutil.rmtree(target / rel, ignore_errors=True)
        subprocess.run(["cp", "-a", str(venv / rel), str(target / rel)], check=True,
                       capture_output=True, text=True)
    return target


class Worker:
    def __init__(self, args):
        self.args = args
        self.root = Path(args.root).resolve()
        self.runs = Path(args.runs).resolve()
        self.task = args.task
        self.entry = task_entry(self.root, self.task)
        self.base = self.runs / self.task.replace("/", "__")
        self.summary_path = self.base / "summary.json"
        self.scratch = self.base / ".scratch"
        self.taskenv = {}
        if args.taskenv:
            data = read_json(Path(args.taskenv), {})
            if not isinstance(data, dict):
                raise SystemExit(f"--taskenv is not a JSON object: {args.taskenv}")
            self.taskenv = data.get(self.task, {}) or {}
        venv = self.taskenv.get("venv") or args.venv
        self.venv = Path(venv).expanduser() if venv else None
        if args.executor == "rootless" and self.venv is None:
            raise SystemExit("--venv (or taskenv venv) is required for the rootless executor")
        self.plugin = Path(args.plugin).expanduser() if args.plugin else None
        self.agent_env = list(args.agent_env or [])
        for name in self.agent_env:
            if name not in os.environ:
                raise SystemExit(f"--agent-env {name}: not set in this process")
        self.summary = self.load_summary()

    def load_summary(self) -> dict:
        summary = read_json(self.summary_path, {}) or {}
        if summary and (summary.get("run_id") != self.args.run_id
                        or summary.get("plan_sha256") != self.args.plan_sha):
            raise SystemExit(
                f"{self.summary_path} belongs to another run; use the matching --out or a "
                "fresh run")
        summary.setdefault("task", self.task)
        summary.setdefault("run_id", self.args.run_id)
        summary.setdefault("plan_sha256", self.args.plan_sha)
        summary.setdefault("plugin_sha256", self.args.plugin_sha)
        summary.setdefault("attempts", {})
        summary.setdefault("steps", {})
        return summary

    def save(self) -> None:
        atomic_write(self.summary_path, json.dumps(self.summary, indent=2, ensure_ascii=False))

    def log(self, message: str) -> None:
        print(f"[{time.strftime('%H:%M:%S')}] {self.task} {message}", flush=True)

    def cli_base(self, action: str, out: Path) -> list[str]:
        args = self.args
        cmd = shlex.split(args.cli) + [
            "benchmarks", "external", action,
            "--root", str(self.root), "--task", self.task,
            "--executor", args.executor, "--output", str(out),
        ]
        if args.executor == "rootless":
            cmd += ["--proot", args.proot, "--python-env", "@VENV@"]
        return cmd

    def step_env(self, binds: list) -> dict:
        env = dict(os.environ)
        if self.args.pythonpath:
            env["PYTHONPATH"] = self.args.pythonpath
        overlay = self.taskenv.get("overlay")
        if overlay:
            env["PHI_OVERLAY"] = overlay
            env["PHI_OVERLAY_REPLACE"] = ",".join(self.taskenv.get("replace") or [])
        extra = list(binds) + list(self.taskenv.get("binds") or [])
        if extra:
            env["PHI_EXTRA_BINDS"] = json.dumps(extra)
        return env

    def run_step(self, name: str, argv: list[str], timeout: float) -> dict:
        """Run one CLI step with a private venv copy and per-step copied binds."""
        self.scratch.mkdir(parents=True, exist_ok=True)
        if self.args.executor == "rootless":
            env_copy = venv_copy(self.venv, self.scratch,
                                 list(self.taskenv.get("deepcopy") or []))
        else:
            env_copy = self.venv
        binds = list(self.args.bind or [])
        copied = []
        for host, container in self.taskenv.get("copybinds") or []:
            copy = self.scratch / f"bind{len(copied)}-{time.time_ns()}"
            subprocess.run(["cp", "-a", str(host), str(copy)], check=True,
                           capture_output=True, text=True)
            copied.append(copy)
            binds.append([str(copy), container])
        argv = [str(env_copy) if token == "@VENV@" else token for token in argv]
        log_path = self.base / f"{name}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        started = time.time()
        timed_out = False
        try:
            with log_path.open("w", encoding="utf-8") as handle:
                code = subprocess.run(argv, stdout=handle, stderr=subprocess.STDOUT,
                                      cwd=str(self.root), env=self.step_env(binds),
                                      timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            code, timed_out = None, True
        except OSError as error:
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"step did not start: {error}\n")
            code = None
        finally:
            if self.args.executor == "rootless":
                shutil.rmtree(env_copy, ignore_errors=True)
            for copy in copied:
                shutil.rmtree(copy, ignore_errors=True)
        return {"rc": code, "timed_out": timed_out, "seconds": round(time.time() - started, 1),
                "log": str(log_path)}

    def mode(self, mode: str, out: Path, extra: list[str], step: str, timeout: float) -> dict:
        argv = self.cli_base("run", out) + ["--mode", mode, *extra]
        result = self.run_step(step, argv, timeout)
        record = read_json(out / mode / "result.json", {}) or {}
        result["status"] = record.get("status")
        return result

    def agent_summary(self, out: Path, step: dict) -> dict:
        record = read_json(out / "agent" / "result.json", {}) or {}
        score = record.get("score") or {}
        landing = record.get("landing") or {}
        log = out / "agent" / "landing.log"
        lines = log.read_text(errors="replace").splitlines() if log.is_file() else []
        calls = [line.strip()[:300] for line in lines if "inferrsi.py" in line]
        tokens = None
        for index in range(len(lines) - 1, -1, -1):
            if lines[index].strip() == "tokens used" and index + 1 < len(lines):
                try:
                    tokens = int(lines[index + 1].replace(",", "").strip())
                except ValueError:
                    tokens = None
                break
        return {
            **step,
            "status": record.get("status"),
            "landing_exit": landing.get("exit_code"),
            "landing_timed_out": landing.get("timed_out"),
            "landing_seconds": landing.get("seconds"),
            "speedup": score.get("speedup"),
            "reward": score.get("reward"),
            "hard": score.get("hard_fail_reasons"),
            "patch_bytes": record.get("model_patch_bytes"),
            "grading_assets_exposed": record.get("grading_assets_exposed_to_agent"),
            "plugin_sha256": (record.get("inferrsi") or {}).get("content_sha256"),
            "inferrsi_calls": calls,
            "tokens": tokens,
            "dir": str(out),
        }

    def write_ref(self, measured: float) -> list[str]:
        """Replace the suite's H20 anchor with this host's measured median (as the host does)."""
        package = self.root / self.entry["package_root"]
        written = []
        ref = package / "tests/ref_speedup.txt"
        if ref.is_file():
            ref.write_text(f"{measured:.6g}\n", encoding="utf-8")
            written.append(str(ref))
        manifest = package / "tests/verifier-correctness-manifest.json"
        if manifest.is_file():
            data = read_json(manifest, {}) or {}
            block = data.get("ref_speedup")
            if isinstance(block, (int, float)):
                data["ref_speedup"] = measured
                data["ref_speedup_calibrated_on"] = "phibench_ab host calibration; median of 3"
                atomic_write(manifest, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
                written.append(str(manifest))
            elif isinstance(block, dict):
                block["value"] = measured
                block["status"] = "CALIBRATED"
                block["calibrated_on"] = "phibench_ab host calibration; median of 3"
                atomic_write(manifest, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
                written.append(str(manifest))
        return written

    def calibrated(self) -> bool:
        return self.entry.get("ref_speedup") is not None and not self.args.no_calibration

    def settled_arm(self, arm: str) -> bool:
        step = self.summary["steps"].get(arm)
        if not step:
            return False
        if step.get("status") == "graded":
            return True
        return int(self.summary["attempts"].get(arm, 0)) >= self.args.max_attempts

    def run(self) -> int:
        steps = self.summary["steps"]
        agent_t = toml_timeout(self.root, self.entry, "agent", 2400)
        verify_t = toml_timeout(self.root, self.entry, "verifier", 1800)
        if "probe" not in steps:
            out = self.base / "probe"
            shutil.rmtree(out, ignore_errors=True)
            command = "test ! -e /tests && test ! -e /solution && echo PROBE-OK"
            steps["probe"] = self.mode("agent", out, ["--agent-command", command], "probe",
                                       STEP_MARGIN + verify_t)
            self.save()
            self.log(f"probe {steps['probe'].get('status')}")
        if self.calibrated() and "calibration" not in steps:
            runs, speeds = [], []
            for index in (1, 2, 3):
                out = self.base / f"cal{index}"
                shutil.rmtree(out, ignore_errors=True)
                step = self.mode("oracle", out, [], f"cal{index}", STEP_MARGIN + verify_t)
                record = read_json(out / "oracle" / "result.json", {}) or {}
                score = record.get("score") or {}
                speeds.append(score.get("speedup"))
                runs.append({"rc": step.get("rc"), "status": record.get("status"),
                             "speedup": score.get("speedup"), "reward": score.get("reward"),
                             "hard": score.get("hard_fail_reasons")})
            good = [run["speedup"] for run in runs
                    if isinstance(run["speedup"], (int, float)) and run["speedup"] > 0
                    and not run["hard"]]
            measured = statistics.median(good) if len(good) == 3 else None
            steps["calibration"] = {
                "runs": runs, "speeds": speeds, "median": measured,
                "written": self.write_ref(measured) if measured is not None else [],
            }
            self.save()
            self.log(f"calibration {speeds} median {measured}")
        if "selfcheck" not in steps:
            out = self.base / "selfcheck"
            shutil.rmtree(out, ignore_errors=True)
            argv = self.cli_base("selfcheck", out) + [
                "--oracle-tolerance", str(self.args.oracle_tolerance)]
            step = self.run_step("selfcheck", argv, 3 * (STEP_MARGIN + verify_t))
            check = read_json(out / "selfcheck.json", {}) or {}
            steps["selfcheck"] = {**step, "verdict": check.get("verdict"),
                                  "checks": check.get("checks")}
            self.save()
            self.log(f"selfcheck {check.get('verdict')}")
        extra = ["--agent-command", self.args.agent_command]
        for name in self.agent_env:
            extra += ["--agent-env", name]
        for arm in ("control", "inferrsi"):
            if self.settled_arm(arm):
                continue
            self.summary["attempts"][arm] = int(self.summary["attempts"].get(arm, 0)) + 1
            out = self.base / arm
            shutil.rmtree(out, ignore_errors=True)
            arm_extra = list(extra)
            if arm == "inferrsi":
                if not self.plugin:
                    raise SystemExit("--plugin is required for the InferRSI arm")
                arm_extra += ["--inferrsi-plugin", str(self.plugin)]
            step = self.mode("agent", out, arm_extra, arm, agent_t + verify_t + 900)
            steps[arm] = self.agent_summary(out, step)
            patch = out / "agent" / "root" / "logs" / "artifacts" / "model.patch"
            if patch.is_file():
                shutil.copy2(patch, self.base / f"{arm}.patch")
            self.save()
            self.log(f"{arm} status={steps[arm].get('status')} "
                     f"reward={steps[arm].get('reward')} attempt="
                     f"{self.summary['attempts'][arm]}")
        if self.settled_arm("control") and self.settled_arm("inferrsi"):
            if "finished" not in self.summary:
                self.summary["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                self.save()
        graded = all((steps.get(arm) or {}).get("status") == "graded"
                     for arm in ("control", "inferrsi"))
        return 0 if graded else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run one Φ-Bench task with both arms")
    parser.add_argument("--root", required=True, type=Path, help="Φ-Bench clone")
    parser.add_argument("--runs", required=True, type=Path, help="isolated runs directory")
    parser.add_argument("--task", required=True, help="task ID, e.g. kfc/<name>")
    parser.add_argument("--venv", type=Path, help="default task Python environment")
    parser.add_argument("--taskenv", type=Path, help="per-task venv/overlay/binds JSON")
    parser.add_argument("--plugin", type=Path, help="built InferRSI Codex plugin directory")
    parser.add_argument("--agent-command", required=True)
    parser.add_argument("--agent-env", action="append", default=[], metavar="NAME")
    parser.add_argument("--executor", choices=("rootless", "docker"), default="rootless")
    parser.add_argument("--proot", default="proot")
    parser.add_argument("--cli", default=f"{sys.executable} -m inferrsi",
                        help="command that runs the InferRSI CLI")
    parser.add_argument("--pythonpath", help="PYTHONPATH for the CLI (source checkout)")
    parser.add_argument("--bind", action="append", default=[], metavar="HOST:CONTAINER",
                        help="extra proot bind (repeatable)")
    parser.add_argument("--oracle-tolerance", type=float, default=0.03)  # 来源：run-one.py 的容差
    parser.add_argument("--max-attempts", type=int, default=3,  # 来源：driver3.py 的尝试上限
                        help="attempts per arm across resumed invocations")
    parser.add_argument("--no-calibration", action="store_true",
                        help="do not re-measure the suite anchor on this host")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--plan-sha", required=True)
    parser.add_argument("--plugin-sha")
    args = parser.parse_args(argv)
    if args.max_attempts < 1:
        parser.error("--max-attempts must be at least 1")
    binds = []
    for item in args.bind:
        host, _, container = item.partition(":")
        binds.append([host, container])
    args.bind = binds
    return Worker(args).run()


if __name__ == "__main__":
    sys.exit(main())
