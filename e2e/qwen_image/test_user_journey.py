"""One opt-in, unattended Codex optimization and independent Ascend A2 measurement."""

import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path
from statistics import median

import pytest

from inferrsi.harness.candidates import identity as source_digest

CASE = Path(__file__).resolve().parent
OPTIMIZATION_ROUNDS = 3
CASE_GAIN_FLOOR_PCT = 10


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, stdout=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
    ).stdout


def checkout(repo, revision, destination):
    subprocess.run(["git", "clone", "--quiet", "--no-local", "--no-checkout",
                    str(repo), str(destination)], check=True, stdin=subprocess.DEVNULL)
    git(destination, "checkout", "--quiet", "--detach", revision)
    if git(destination, "rev-parse", "HEAD").decode().strip() != revision:
        raise ValueError("Use the full baseline commit from the acceptance issue")


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_minimum_gain():
    minimum = float(os.environ["QWEN_E2E_MIN_GAIN_PCT"])
    if not math.isfinite(minimum) or minimum < CASE_GAIN_FLOOR_PCT:
        raise ValueError(f"This E2E case requires a gain floor of at least {CASE_GAIN_FLOOR_PCT}%")
    return minimum


def performance_verdict(gain, minimum, noise, failed_seeds):
    if failed_seeds or gain <= Decimal(str(minimum)):
        return "FAIL"
    return "PASS" if gain > Decimal(str(noise)) else "INCONCLUSIVE"


def run_logged(argv, cwd, logfile, timeout, prompt=None):
    # On the A2 host, stop this run's local process group if its deadline expires.
    with logfile.open("wb") as log, subprocess.Popen(
        argv, cwd=cwd, start_new_session=True, stdout=log, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL if prompt is None else subprocess.PIPE,
    ) as child:
        try:
            child.communicate(input=prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
            raise
        if child.returncode:
            raise RuntimeError(f"{Path(argv[0]).name} exited {child.returncode}; see "
                               f"{logfile.name}")


def optimize(project, checkpoint, output, timeout):
    sources = ["vllm_omni"]
    starting_sha = source_digest(project, sources)
    agent_runs = output / "agent-runs"
    agent_runs.mkdir()
    prompt = (CASE / "request.txt").read_text(encoding="utf-8").strip()
    prompt += (
        f"\n模型目录：{checkpoint}。冻结的测量程序：{CASE / 'measure.py'}，"
        "依次传入源码目录、模型目录、新输出目录。"
        f"在 {agent_runs} 下依次创建 loop-01 到 loop-{OPTIMIZATION_ROUNDS:02d}。"
        "每次以当前项目的累计源码为起点，用 InferRSI campaign start "
        "（--rounds 1 --round-mode exact --include vllm_omni）冻结本轮基线。"
        "随后诊断、改进源码并用 campaign round 测量当前候选与本轮基线。"
        "使用本轮像素一致的候选源码和实测反馈继续下一轮。"
        "第三轮的累计实现留在当前项目的 vllm_omni/ 下，供测试端与原始基线独立复测。"
    )
    (output / "request.txt").write_text(prompt + "\n", encoding="utf-8")
    command = ["codex", "--ask-for-approval", "never", "exec", "--sandbox", "workspace-write",
               "--add-dir", str(agent_runs),
               "--json", "--output-last-message", str(output / "final-reply.txt")]
    if model := os.environ.get("QWEN_E2E_CODEX_MODEL"):
        command += ["--model", model]
    run_logged([*command, "-"], project, output / "codex.jsonl", timeout, prompt.encode("utf-8"))

    if not (output / "final-reply.txt").read_text(encoding="utf-8").strip():
        raise ValueError("The Codex run did not deliver a final reply")
    loops = []
    seen = {starting_sha}
    for number in range(1, OPTIMIZATION_ROUNDS + 1):
        campaign = agent_runs / f"loop-{number:02d}"
        plan = json.loads((campaign / "plan.json").read_bytes())
        state = json.loads((campaign / "state.json").read_bytes())
        if (plan["task_source"] != "project" or Path(plan["working_candidate"]) != project
                or plan["round_mode"] != "exact" or plan["round_limit"] != 1
                or plan["candidate_includes"] != sources
                or plan["baseline_path"] != "frozen/baseline"
                or state["state"] not in ("active", "completed") or state.get("pending") is not None
                or len(state["rounds"]) != 1):
            raise ValueError(f"Loop {number} requires one completed project round")
        if (plan["baseline_sha256"] != starting_sha
                or source_digest(campaign / "frozen/baseline", sources) != starting_sha):
            raise ValueError(f"Loop {number} did not start from the previous cumulative source")

        observation = state["rounds"][0]
        assessment = observation["assessment"]
        metrics = assessment.get("metrics", {})
        if (assessment["status"] != "completed" or assessment.get("quality_passed") is not True
                or any(type(ms) not in (int, float) or not math.isfinite(ms) or ms <= 0
                       for ms in (metrics.get("baseline"), metrics.get("candidate")))):
            raise ValueError(f"Loop {number} requires complete timings and pixel parity")
        snapshot = (campaign / observation["path"] / plan["candidate_name"]).resolve()
        end_sha = observation["candidate_sha256"]
        if (not snapshot.is_relative_to(campaign.resolve()) or end_sha in seen
                or source_digest(snapshot, sources) != end_sha):
            raise ValueError(f"Loop {number} did not deliver a new measured snapshot")
        loops.append({"number": number, "starting_source_sha256": starting_sha,
                      "candidate_sha256": end_sha, "starting_ms": metrics["baseline"],
                      "candidate_ms": metrics["candidate"]})
        starting_sha = end_sha
        seen.add(end_sha)
    if source_digest(project, sources) != starting_sha:
        raise ValueError("The delivered source must be the third loop's cumulative implementation")
    return loops


def measure(source, checkpoint, output, timeout):
    output.mkdir()
    run_logged([sys.executable, str(CASE / "measure.py"), str(source), str(checkpoint),
                str(output)], source, output / "worker.log", timeout)


def sample(source, checkpoint, output, timeout, workload):
    from PIL import Image

    measure(source, checkpoint, output, timeout)
    receipt = json.loads((output / "result.json").read_bytes())
    times = receipt["latencies_ms"]
    seeds = [row["seed"] for row in workload["requests"]]
    if (receipt["seeds"] != seeds or len(times) != len(seeds)
            or len(receipt["warmup_ms"]) != len(workload["warmups"])
            or any(not math.isfinite(t) or t <= 0 for t in [*times, *receipt["warmup_ms"]])):
        raise ValueError("Missing or invalid raw timing samples")
    grid = receipt["sampling_grid"]
    trace_seeds = {str(row["seed"]) for row in workload["warmups"] + workload["requests"]}
    if not isinstance(grid, dict) or set(grid) != trace_seeds:
        raise ValueError("Missing per-request sampling grid evidence")
    for trace in grid.values():
        steps = trace["steps"]
        if (not isinstance(steps, list) or not steps or trace["step_count"] != len(steps)
                or any(set(step) != {"timestep", "sigma", "next_sigma"}
                       or any(type(value) not in (int, float) or not math.isfinite(value)
                              for value in step.values())
                       for step in steps)):
            raise ValueError("Invalid effective sampling grid")
    pixels = {}
    for seed in seeds:
        with Image.open(output / f"seed-{seed}.png") as image:
            if image.mode != "RGBA" or image.size != (workload["width"], workload["height"]):
                raise ValueError("Unexpected decoded image format")
            pixels[seed] = hashlib.sha256(image.tobytes()).hexdigest()
    identity = {k: receipt[k] for k in ("device", "sample_sigmas", "sampling_grid",
                                         "workload_sha256", "model_index_sha256")}
    return median(times), pixels, identity


def verify_source(repo, expected_tree, expected_source):
    if (git(repo, "write-tree").decode().strip() != expected_tree
            or git(repo, "diff", "--name-only", "--", "vllm_omni")
            or source_digest(repo, ["vllm_omni"]) != expected_source):
        raise ValueError("The measured source changed after checkout or patch reconstruction")


def test_codex_optimizes_qwen_image_on_a2(tmp_path):
    parent = Path(os.environ.get("QWEN_E2E_RESULTS", tmp_path)).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="qwen-a2-", dir=parent))
    print(f"E2E results: {output}", flush=True)
    report = {"verdict": "INCONCLUSIVE", "stage": "preflight",
              "required_optimization_rounds": OPTIMIZATION_ROUNDS}
    try:
        repo = Path(os.environ["QWEN_E2E_REPO"]).resolve(strict=True)
        checkpoint = Path(os.environ["QWEN_E2E_CHECKPOINT"]).resolve(strict=True)
        revision = os.environ["QWEN_E2E_REVISION"]
        timeout = int(os.environ.get("QWEN_E2E_TIMEOUT_SECONDS", "7200"))
        minimum = read_minimum_gain()
        if timeout <= 0:
            raise ValueError("Timeout must be positive")
        workload = json.loads((CASE / "workload.json").read_bytes())
        baseline, project, candidate = (output / n for n in ("baseline", "optimize", "candidate"))
        for tree in (baseline, project):
            checkout(repo, revision, tree)
        baseline_tree = git(baseline, "write-tree").decode().strip()
        baseline_source = source_digest(baseline, ["vllm_omni"])
        first, reference, identity = sample(baseline, checkpoint, output / "preflight-a",
                                            timeout, workload)
        second, pixels, other = sample(baseline, checkpoint, output / "preflight-b",
                                       timeout, workload)
        if (pixels != reference or identity != other
                or identity["sample_sigmas"] != workload["sample_sigmas"]
                or any(trace["step_count"] != len(workload["sample_sigmas"])
                       for trace in identity["sampling_grid"].values())
                or identity["workload_sha256"] != hashlib.sha256(
                    (CASE / "workload.json").read_bytes()).hexdigest()):
            raise ValueError("Baseline A/A pixels or environment changed before optimization")
        noise = 100 * abs(second - first) / first
        report.update(baseline_revision=revision, environment=identity, aa_ms=[first, second],
                      noise_pct=noise, min_gain_pct=minimum)
        write_json(output / "frozen.json", report)
        report["stage"] = "codex"
        loops = optimize(project, checkpoint, output, timeout)
        report.update(completed_optimization_rounds=len(loops), optimization_loops=loops)

        report["stage"] = "reconstruct"
        git(project, "add", "-A", "--", "vllm_omni")
        patch = git(project, "diff", "--cached", "--binary", "--full-index", revision,
                    "--", "vllm_omni")
        if not patch:
            report.update(verdict="FAIL", error="Codex finished without delivering a source change")
            pytest.fail(report["error"])
        patchfile = output / "candidate.patch"
        patchfile.write_bytes(patch)
        checkout(repo, revision, candidate)
        git(candidate, "apply", "--index", "--binary", str(patchfile))
        selected = git(project, "write-tree").decode().strip()
        rebuilt = git(candidate, "write-tree").decode().strip()
        candidate_source = source_digest(candidate, ["vllm_omni"])
        if (git(project, "rev-parse", selected + ":vllm_omni")
                != git(candidate, "rev-parse", rebuilt + ":vllm_omni")
                or candidate_source != loops[-1]["candidate_sha256"]):
            report.update(verdict="FAIL",
                          error="Patch does not reconstruct the third measured snapshot")
            pytest.fail(report["error"])
        report.update(candidate_tree=rebuilt, candidate_source_sha256=candidate_source,
                      patch_sha256=hashlib.sha256(patch).hexdigest())

        report["stage"] = "independent_retest"
        scores = {"baseline": [], "candidate": []}
        failed_seeds = set()
        for i, pair in enumerate(("AB", "BA", "AB"), 1):
            for arm in pair:
                name, tree = ("baseline", baseline) if arm == "A" else ("candidate", candidate)
                expected_tree = baseline_tree if arm == "A" else rebuilt
                expected_source = baseline_source if arm == "A" else candidate_source
                verify_source(tree, expected_tree, expected_source)
                value, actual, runtime = sample(tree, checkpoint, output / f"{i:02}-{name}",
                                                timeout, workload)
                verify_source(tree, expected_tree, expected_source)
                if runtime != identity or (name == "baseline" and actual != reference):
                    raise ValueError("Independent inputs or effective sampling grid changed")
                failed_seeds.update(seed for seed in reference if actual[seed] != reference[seed])
                scores[name].append(value)
        before, after = (median(scores[name]) for name in ("baseline", "candidate"))
        baseline_ms = Decimal(str(before))
        gain = 100 * (baseline_ms - Decimal(str(after))) / baseline_ms
        report.update(stage="finished", group_medians_ms=scores, baseline_ms=before,
                      candidate_ms=after, reduction_ms=before - after, reduction_pct=float(gain),
                      speedup=before / after, quality_passed=len(reference) - len(failed_seeds),
                      quality_total=len(reference), failed_seeds=sorted(failed_seeds))
        report["verdict"] = performance_verdict(gain, minimum, noise, failed_seeds)
        assert report["verdict"] == "PASS", report
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        write_json(output / "result.json", report)
        print(json.dumps(report, ensure_ascii=False), flush=True)
