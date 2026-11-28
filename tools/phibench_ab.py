#!/usr/bin/env python3
"""One command for the Φ-Bench A/B run: draw N tasks, run both arms, print one score.

The control arm is plain Codex; the experiment arm is Codex plus the built
InferRSI Codex plugin. Every task runs the same sequence (probe, three oracle
calibrations, selfcheck, control, InferRSI) in an isolated run directory, so a
new ``--n`` really runs new tasks instead of re-scoring old summaries.

Compared with the first host script, this entry point:

* puts each run under ``<out>/runs`` and refuses to reuse summaries from another
  run (run id, plan hash and plugin hash are checked);
* defaults to a non-zero exit when any selected task did not produce both
  scores, with ``--allow-partial`` to accept a partial run explicitly;
* reports the quality of the scored set (selfcheck, host calibration, empty
  patches, timeouts) and the score after excluding those tasks, instead of
  presenting the raw mean difference as a stable result.

usage:
  phibench_ab.py --root phibench --plugin /path/codex-plugin --venv /path/venv
  phibench_ab.py --n 20 --seed 1 --root phibench --plugin /path/codex-plugin ...
  phibench_ab.py --score-only --out ab-20261128-120000
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import shlex
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TOOL = Path(__file__).resolve()
WORKER = TOOL.with_name("phibench_task.py")
# 来源：沿用工作脚本 compare.py 的 SKIPPED，该题判分会扫描整机可写挂载。
SKIP_GPU = "e2e/a8-peft-adapter-byte-golf"
# 来源：沿用工作脚本 driver3.py 的每题最多 3 次尝试。
MAX_ATTEMPTS = 3
# 来源：0.03 沿用工作脚本 run-one.py 的 selfcheck 容差。
ORACLE_TOLERANCE = 0.03
# 来源：沿用工作脚本 driver3.py 的 4 个 GPU worker、2 个 CPU worker。
GPU_WORKERS = 4
CPU_WORKERS = 2  # 来源：同上，driver3.py 的 CPU worker 数
# The outer pool has one thread per queue (GPU and CPU).
QUEUES = 2  # 来源：driver3.py 的 GPU/CPU 两个队列


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return default


def load_plan(root: Path) -> list[dict]:
    index = read_json(root / "tasks_index.json")
    if not isinstance(index, dict) or not isinstance(index.get("tasks"), list):
        raise ValueError(f"not a Φ-Bench clone (missing tasks_index.json): {root}")
    plan = []
    for entry in index["tasks"]:
        task = f"{entry.get('bench')}/{entry.get('task')}"
        if task == SKIP_GPU:
            continue
        plan.append({**entry, "task": task})
    if not plan:
        raise ValueError(f"no runnable tasks in {root / 'tasks_index.json'}")
    return plan


def stratum(entry: dict) -> str:
    return f"{entry['task'].split('/', 1)[0]}-{'GPU' if entry.get('gpus') else 'CPU'}"


def allocate(sizes: dict[str, int], n: int) -> dict[str, int]:
    """Split n over the strata in proportion to their sizes (largest remainder)."""
    total = sum(sizes.values())
    if not 0 < n <= total:
        raise ValueError(f"n must be between 1 and {total}, got {n}")
    quota = {key: n * size / total for key, size in sizes.items()}
    out = {key: int(value) for key, value in quota.items()}
    rest = sorted(sizes, key=lambda key: (-(quota[key] - out[key]), key))
    for key in rest[: n - sum(out.values())]:
        out[key] += 1
    return out


def select(plan: list[dict], n: int | None, seed: int) -> list[dict]:
    """The whole plan, or n tasks drawn with a fixed seed, keeping the suite's type mix."""
    if n is None:
        return list(plan)
    groups: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for entry in plan:
        key = stratum(entry)
        groups[key.split("-")[0]][key].append(entry["task"])
    per_bench = allocate({bench: sum(map(len, group.values()))
                          for bench, group in groups.items()}, n)
    rng = random.Random(seed)
    picked = set()
    for bench in sorted(groups):
        if not per_bench[bench]:
            continue
        counts = allocate({key: len(value) for key, value in groups[bench].items()},
                          per_bench[bench])
        for key in sorted(groups[bench]):
            picked.update(rng.sample(sorted(groups[bench][key]), counts[key]))
    return [entry for entry in plan if entry["task"] in picked]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_dir(path: Path) -> str | None:
    """Content hash of a directory, ignoring .git; None when the path is absent."""
    path = Path(path)
    if not path.is_dir():
        return None
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*")):
        if item.is_dir() or ".git" in item.parts:
            continue
        digest.update(str(item.relative_to(path)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.read_bytes())
    return digest.hexdigest()


def execution_settings(args) -> dict:
    """Everything that changes how a task runs; saved so `--resume --out` restores it."""
    return {
        "root": str(args.root),
        "venv": str(Path(args.venv).resolve()) if args.venv else None,
        "taskenv": str(Path(args.taskenv).resolve()) if args.taskenv else None,
        "pythonpath": args.pythonpath,
        "agent_env": sorted(args.agent_env or []),
        "bind": sorted(args.bind or []),
        "proot": args.proot,
        "gpu_prefix": args.gpu_prefix,
        "cpu_prefix": args.cpu_prefix,
        "gpu_workers": args.gpu_workers,
        "cpu_workers": args.cpu_workers,
        "no_calibration": bool(args.no_calibration),
    }


def identity(args, chosen: list[dict], plugin_sha: str | None) -> dict:
    body = {
        "tasks": [entry["task"] for entry in chosen],
        "n": args.n, "seed": args.seed, "plugin_sha256": plugin_sha,
        "agent_command": args.agent_command, "cli": args.cli,
        "executor": args.executor, "oracle_tolerance": args.oracle_tolerance,
        "max_attempts": args.max_attempts,
        **execution_settings(args),
    }
    return {**body, "plan_sha256": sha256_text(json.dumps(body, sort_keys=True))}


def task_dir(out: Path, task: str) -> Path:
    return out / "runs" / task.replace("/", "__")


def task_summary(out: Path, task: str) -> dict:
    return read_json(task_dir(out, task) / "summary.json", {}) or {}


def finished(summary: dict, ident: dict) -> bool:
    """A summary is reusable only when it belongs to this plan and has no open work."""
    return bool(summary.get("finished")) \
        and summary.get("run_id") == ident["run_id"] \
        and summary.get("plan_sha256") == ident["plan_sha256"] \
        and summary.get("plugin_sha256") == ident["plugin_sha256"]


def worker_argv(args, task: str, run_dir: Path, ident: dict) -> list[str]:
    argv = [
        sys.executable, str(WORKER),
        "--root", str(args.root),
        "--runs", str((run_dir / "runs").resolve()),
        "--task", task,
        "--plugin", str(Path(args.plugin).resolve()),
        "--agent-command", args.agent_command,
        "--executor", args.executor,
        "--proot", args.proot,
        "--cli", args.cli,
        "--oracle-tolerance", str(args.oracle_tolerance),
        "--max-attempts", str(args.max_attempts),
        "--run-id", ident["run_id"],
        "--plan-sha", ident["plan_sha256"],
        "--plugin-sha", ident["plugin_sha256"] or "",
    ]
    if args.venv:
        argv += ["--venv", str(Path(args.venv).resolve())]
    if args.taskenv:
        argv += ["--taskenv", str(Path(args.taskenv).resolve())]
    if args.pythonpath:
        argv += ["--pythonpath", args.pythonpath]
    if args.no_calibration:
        argv += ["--no-calibration"]
    for name in args.agent_env:
        argv += ["--agent-env", name]
    for item in args.bind:
        argv += ["--bind", item]
    return argv


def run_one(args, task: str, run_dir: Path, ident: dict, prefix: str) -> bool:
    """Run one worker; return True when the worker exited normally."""
    prefix = (prefix or "").format(task=task, out=run_dir)
    argv = shlex.split(prefix) + worker_argv(args, task, run_dir, ident) if prefix \
        else worker_argv(args, task, run_dir, ident)
    log = run_dir / "logs" / (task.replace("/", "__") + ".log")
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"\n===== {time.strftime('%F %T')} {task} =====\n")
        handle.flush()
        try:
            code = subprocess.run(argv, stdout=handle, stderr=subprocess.STDOUT,
                                  cwd=str(run_dir), env=dict(os.environ)).returncode
        except OSError as error:
            handle.write(f"worker did not start: {error}\n")
            return False
    return code in (0, 1)


def run_pool(args, tasks: list[dict], run_dir: Path, ident: dict, workers: int,
             prefix: str) -> None:
    if not tasks or workers <= 0:
        return

    def one(entry):
        task = entry["task"]
        if finished(task_summary(run_dir, task), ident):
            return
        run_one(args, task, run_dir, ident, prefix)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, tasks))


def run(args, chosen: list[dict], run_dir: Path, ident: dict) -> dict:
    before = {entry["task"]: finished(task_summary(run_dir, entry["task"]), ident)
              for entry in chosen}
    gpu = [entry for entry in chosen if entry.get("gpus")]
    cpu = [entry for entry in chosen if not entry.get("gpus")]
    for _ in range(args.max_attempts):
        pending = [entry for entry in chosen
                   if not finished(task_summary(run_dir, entry["task"]), ident)]
        if not pending:
            break
        pending_tasks = {entry["task"] for entry in pending}
        with ThreadPoolExecutor(max_workers=QUEUES) as outer:
            outer.submit(run_pool, args, [e for e in gpu if e["task"] in pending_tasks],
                         run_dir, ident, args.gpu_workers, args.gpu_prefix)
            outer.submit(run_pool, args, [e for e in cpu if e["task"] in pending_tasks],
                         run_dir, ident, args.cpu_workers, args.cpu_prefix)
    after = {entry["task"]: finished(task_summary(run_dir, entry["task"]), ident)
             for entry in chosen}
    new = [task for task, done in after.items() if not before[task] and done]
    reused = [task for task, done in after.items() if before[task] and done]
    skipped = [task for task, done in after.items() if not done]
    return {"new": new, "reused": reused, "skipped": skipped}


def finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def score_tasks(chosen: list[dict], run_dir: Path, ident: dict | None = None) -> dict:
    rows, valid = [], []
    for entry in chosen:
        task = entry["task"]
        summary = task_summary(run_dir, task)
        steps = summary.get("steps") or {}
        cal = steps.get("calibration") or {}
        check = steps.get("selfcheck") or {}
        row = {"task": task, "bench": entry.get("bench"),
               "device": "GPU" if entry.get("gpus") else "CPU",
               "class": entry.get("reward_class"), "selfcheck": check.get("verdict"),
               "ref_l20": cal.get("median"), "state": "missing",
               "probe_exposed": (steps.get("probe") or {}).get("grading_assets_exposed")}
        if not summary:
            rows.append(row)
            continue
        if row["probe_exposed"] is True:
            row["state"] = "probe_failed"
            rows.append(row)
            continue
        if ident and (summary.get("run_id") != ident.get("run_id")
                      or summary.get("plan_sha256") != ident.get("plan_sha256")
                      or summary.get("plugin_sha256") != ident.get("plugin_sha256")):
            row["state"] = "other_run"
            rows.append(row)
            continue
        for arm in ("control", "inferrsi"):
            step = steps.get(arm)
            if step:
                row[arm] = {key: step.get(key) for key in
                            ("status", "reward", "speedup", "hard", "patch_bytes",
                             "tokens", "landing_seconds", "landing_timed_out")}
        row["state"] = "done" if "control" in row and "inferrsi" in row else "running"
        c, x = row.get("control") or {}, row.get("inferrsi") or {}
        if c.get("status") == "graded" and x.get("status") == "graded" \
                and finite(c.get("reward")) and finite(x.get("reward")):
            row["verdict"] = ("arm_better" if x["reward"] > c["reward"]
                              else "control_better" if x["reward"] < c["reward"] else "tie")
            valid.append(row)
        elif row["state"] == "done":
            row["verdict"] = "invalid"
        rows.append(row)
    quality = {
        "selfcheck_pass": sum(row.get("selfcheck") == "PASS" for row in valid),
        "selfcheck_fail": sum(row.get("selfcheck") == "FAIL" for row in valid),
        "selfcheck_inconclusive": sum(row.get("selfcheck") == "INCONCLUSIVE" for row in valid),
        "selfcheck_missing": sum(row.get("selfcheck") not in
                                 ("PASS", "FAIL", "INCONCLUSIVE") for row in valid),
        "probe_exposed": sum(row.get("probe_exposed") is True for row in rows),
        "no_calibration": sum(row.get("ref_l20") is None for row in valid),
        "empty_patch": sum(any((row.get(arm) or {}).get("patch_bytes") == 0
                               for arm in ("control", "inferrsi")) for row in valid),
        "timed_out": sum(any((row.get(arm) or {}).get("landing_timed_out")
                             for arm in ("control", "inferrsi")) for row in valid),
    }
    verdicts = defaultdict(int)
    for row in valid:
        verdicts[row["verdict"]] += 1

    def mean(values):
        return sum(values) / len(values) if values else None

    def score_of(items):
        controls = [row["control"]["reward"] for row in items]
        experiments = [row["inferrsi"]["reward"] for row in items]
        return None if not items else mean(experiments) - mean(controls)

    controls = [row["control"]["reward"] for row in valid]
    experiments = [row["inferrsi"]["reward"] for row in valid]
    tokens = [(row["control"].get("tokens"), row["inferrsi"].get("tokens")) for row in valid]
    tokens = [(c, x) for c, x in tokens if c and x]
    return {
        "tasks": len(chosen), "scored": len(valid), "score": score_of(valid),
        "control_mean_reward": mean(controls), "inferrsi_mean_reward": mean(experiments),
        "inferrsi_better": verdicts["arm_better"], "control_better": verdicts["control_better"],
        "tie": verdicts["tie"],
        "control_positive": sum(value > 0 for value in controls),
        "inferrsi_positive": sum(value > 0 for value in experiments),
        "token_change": (sum(x for _, x in tokens) / sum(c for c, _ in tokens) - 1)
        if tokens else None,
        "token_median": [median([c for c, _ in tokens]),
                         median([x for _, x in tokens])] if tokens else None,
        "quality": quality,
        "sensitivity": {
            "exclude_no_calibration": score_of(
                [row for row in valid if row.get("ref_l20") is not None]),
            "exclude_selfcheck_not_pass": score_of(
                [row for row in valid if row.get("selfcheck") == "PASS"]),
            "exclude_empty_patch": score_of(
                [row for row in valid
                 if not any((row.get(arm) or {}).get("patch_bytes") == 0
                            for arm in ("control", "inferrsi"))]),
        },
        "unscored": [{"task": row["task"], "state": row["state"],
                      "verdict": row.get("verdict")} for row in rows
                     if id(row) not in {id(item) for item in valid}],
        "rows": rows,
    }


def median(values):
    values = sorted(values)
    if not values:
        return None
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2


def render(result: dict, counts: dict | None) -> str:
    def fmt(value):
        return "—" if value is None else f"{value:.3g}"

    total = "—" if result["score"] is None else f"{result['score']:+.4f}"
    quality = result["quality"]
    sensitivity = result["sensitivity"]
    if counts is None:
        progress = f"按已有结果出分；选题 {result['tasks']} 道，两组都出分 {result['scored']} 道。"
    else:
        progress = (f"本次新跑 {len(counts['new'])} 道、复用 {len(counts['reused'])} 道、"
                    f"跳过 {len(counts['skipped'])} 道；选题 {result['tasks']} 道，"
                    f"两组都出分 {result['scored']} 道。")
    lines = [
        f"总分（实验组平均 reward − 对照组平均 reward）：{total}",
        progress,
        f"平均 reward：对照 {fmt(result['control_mean_reward'])}，"
        f"实验 {fmt(result['inferrsi_mean_reward'])}；拿到正分：对照 "
        f"{result['control_positive']}，实验 {result['inferrsi_positive']}。",
        f"实验组 reward 更高 {result['inferrsi_better']} 道，对照组更高 "
        f"{result['control_better']} 道，持平 {result['tie']} 道。",
        f"质量：自检 PASS {quality['selfcheck_pass']} / FAIL {quality['selfcheck_fail']} / "
        f"INCONCLUSIVE {quality['selfcheck_inconclusive']} / 缺失 "
        f"{quality['selfcheck_missing']}；无本机标定 "
        f"{quality['no_calibration']}；至少一组空补丁 {quality['empty_patch']}；"
        f"超时 {quality['timed_out']}；判分资产暴露 {quality['probe_exposed']}。",
        f"敏感性：剔除无标定 {fmt(sensitivity['exclude_no_calibration'])}；"
        f"剔除自检非 PASS {fmt(sensitivity['exclude_selfcheck_not_pass'])}；"
        f"剔除空补丁 {fmt(sensitivity['exclude_empty_patch'])}。",
    ]
    if result["token_change"] is not None:
        lines.append(f"token：实验组总量比对照组 {result['token_change']:+.0%}。")
    if result["unscored"]:
        names = "、".join(item["task"] for item in result["unscored"])
        lines.append(f"未出分 {len(result['unscored'])} 道：{names}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="One-command Φ-Bench A/B run")
    parser.add_argument("--root", type=Path, help="Φ-Bench clone (default: the saved run root)")
    parser.add_argument("--out", type=Path, help="run directory (default ab-<time>/)")
    parser.add_argument("--n", type=int, help="number of tasks (default: all)")
    parser.add_argument("--seed", type=int, default=0, help="draw seed for --n")
    parser.add_argument("--score-only", action="store_true", help="score an existing run")
    parser.add_argument("--resume", action="store_true", help="continue the run in --out")
    parser.add_argument("--plugin", type=Path, help="built InferRSI Codex plugin directory")
    parser.add_argument("--venv", type=Path, help="default task Python environment")
    parser.add_argument("--taskenv", type=Path, help="per-task venv/overlay/binds JSON")
    parser.add_argument("--agent-command", help="agent command run inside the task tree")
    parser.add_argument("--agent-env", action="append", default=[],
                        help="environment variable forwarded to the agent (repeatable)")
    parser.add_argument("--executor", choices=("rootless", "docker"), default="rootless")
    parser.add_argument("--proot", default="proot")
    parser.add_argument("--cli", default=f"{sys.executable} -m inferrsi",
                        help="command that runs the InferRSI CLI")
    parser.add_argument("--pythonpath", help="PYTHONPATH for the CLI (source checkout)")
    parser.add_argument("--bind", action="append", default=[], metavar="HOST:CONTAINER")
    parser.add_argument("--gpu-prefix", default="", help="wrapper for GPU tasks, e.g. gpu run ...")
    parser.add_argument("--cpu-prefix", default="", help="wrapper for CPU tasks, e.g. taskset ...")
    parser.add_argument("--gpu-workers", type=int, default=GPU_WORKERS)
    parser.add_argument("--cpu-workers", type=int, default=CPU_WORKERS)
    parser.add_argument("--oracle-tolerance", type=float, default=ORACLE_TOLERANCE)
    parser.add_argument("--max-attempts", type=int, default=MAX_ATTEMPTS)
    parser.add_argument("--allow-partial", action="store_true",
                        help="exit 0 even when some selected tasks have no score")
    parser.add_argument("--no-calibration", action="store_true")
    args = parser.parse_args(argv)
    if args.max_attempts < 1:
        parser.error("--max-attempts must be at least 1")
    if args.gpu_workers < 0 or args.cpu_workers < 0:
        parser.error("--gpu-workers/--cpu-workers cannot be negative")
    run_dir = (args.out or Path.cwd() / f"ab-{time.strftime('%Y%m%d-%H%M%S')}").resolve()
    saved = read_json(run_dir / "run.json", {}) or {}
    if args.score_only and not saved:
        parser.error(f"{run_dir} has no run.json to score")
    if args.root is None and saved.get("root"):
        args.root = Path(saved["root"])
    if args.root is None:
        parser.error("--root is required")
    args.root = args.root.resolve()
    if saved and args.resume:
        args.n = saved.get("n") if args.n is None else args.n
        if args.seed == 0 and saved.get("seed"):
            args.seed = saved["seed"]
        args.agent_command = args.agent_command or saved.get("agent_command")
        default_cli = f"{sys.executable} -m inferrsi"
        if args.cli == default_cli and saved.get("cli"):
            args.cli = saved["cli"]
        args.executor = saved.get("executor", args.executor)
        args.oracle_tolerance = saved.get("oracle_tolerance", args.oracle_tolerance)
        args.max_attempts = saved.get("max_attempts", args.max_attempts)
        args.venv = args.venv or (Path(saved["venv"]) if saved.get("venv") else None)
        args.taskenv = args.taskenv or (Path(saved["taskenv"]) if saved.get("taskenv") else None)
        args.plugin = args.plugin or (Path(saved["plugin"]) if saved.get("plugin") else None)
        args.agent_env = args.agent_env or list(saved.get("agent_env") or [])
        args.bind = args.bind or list(saved.get("bind") or [])
        args.gpu_prefix = args.gpu_prefix or saved.get("gpu_prefix") or ""
        args.cpu_prefix = args.cpu_prefix or saved.get("cpu_prefix") or ""
        args.pythonpath = args.pythonpath or saved.get("pythonpath")
        if args.proot == "proot" and saved.get("proot"):
            args.proot = saved["proot"]
        if args.gpu_workers == GPU_WORKERS and saved.get("gpu_workers") is not None:
            args.gpu_workers = saved["gpu_workers"]
        if args.cpu_workers == CPU_WORKERS and saved.get("cpu_workers") is not None:
            args.cpu_workers = saved["cpu_workers"]
        args.no_calibration = bool(args.no_calibration or saved.get("no_calibration"))
    try:
        plan = load_plan(args.root)
        chosen = select(plan, args.n, args.seed)
    except ValueError as error:
        parser.error(str(error))
    if not args.score_only:
        if not args.agent_command:
            parser.error("--agent-command is required for a run")
        if args.plugin is None:
            parser.error("--plugin is required for a run")
        if args.executor != "rootless":
            parser.error("--executor docker cannot run the InferRSI arm; use rootless")
    plugin_sha = sha256_dir(args.plugin) if args.plugin else None
    if not args.score_only and plugin_sha is None:
        parser.error("--plugin must be a directory")
    if saved:
        if not (args.resume or args.score_only):
            parser.error(f"{run_dir} already has a run; use --resume or a new --out")
        ident = saved
        saved_tasks = set(saved.get("tasks") or [])
        chosen = [entry for entry in plan if entry["task"] in saved_tasks]
        if len(chosen) != len(saved_tasks):
            parser.error("the saved run lists tasks that are not in this index")
        if args.resume:
            current = identity(args, chosen, plugin_sha)
            if saved.get("plan_sha256") != current["plan_sha256"]:
                parser.error("--resume arguments differ from the saved plan "
                             "(n/seed/plugin/agent)")
    else:
        if args.resume or args.score_only:
            parser.error(f"{run_dir} has no run.json to resume or score")
        if run_dir.exists() and any(run_dir.iterdir()):
            parser.error(f"{run_dir} is not empty and has no run.json; choose a new --out")
        ident = {**identity(args, chosen, plugin_sha),
                 "run_id": time.strftime("%Y%m%d-%H%M%S")}
        atomic_write(run_dir / "run.json",
                     json.dumps({**ident,
                                 "plugin": (str(Path(args.plugin).resolve())
                                            if args.plugin else None),
                                 "created": time.strftime("%Y-%m-%dT%H:%M:%S")},
                                indent=2, ensure_ascii=False))
    counts = None
    if not args.score_only:
        counts = run(args, chosen, run_dir, ident)
    result = score_tasks(chosen, run_dir, ident)
    result.update(n=ident.get("n", args.n), seed=ident.get("seed", args.seed), mix=dict(sorted(
        ({key: sum(stratum(entry) == key for entry in chosen)
          for key in {stratum(entry) for entry in chosen}}).items())))
    atomic_write(run_dir / "compare.json",
                 json.dumps(result["rows"], indent=1, ensure_ascii=False))
    atomic_write(run_dir / "score.json", json.dumps(result, indent=1, ensure_ascii=False))
    print(render(result, counts))
    print(f"明细：{run_dir}/score.json")
    complete = result["scored"] == len(chosen)
    if not complete and not args.allow_partial:
        print(f"未跑完或未出分：{len(chosen) - result['scored']} 道；"
              "要用 --allow-partial 明确接受部分结果", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
