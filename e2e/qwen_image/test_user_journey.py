"""One opt-in, unattended Codex optimization and independent Ascend A2 measurement."""

import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from statistics import median

import pytest

CASE = Path(__file__).resolve().parent
OPTIMIZATION_ROUNDS = 3


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
    from inferrsi.harness.candidates import identity

    agent_runs = output / "agent-runs"
    agent_runs.mkdir()
    campaign = agent_runs / "campaign"
    prompt = (CASE / "request.txt").read_text(encoding="utf-8").strip()
    prompt += (
        f"\n本机模型目录：{checkpoint}。冻结的测量程序：{CASE / 'measure.py'}，"
        "依次传入源码目录、模型目录、新输出目录。请自主使用本机 InferRSI 的 "
        f"campaign start（--rounds {OPTIMIZATION_ROUNDS} --round-mode exact）、round、final "
        f"完成三轮优化，campaign 目录使用 {campaign}。"
        "将最终选中的生产代码留在当前项目的 vllm_omni/ 下，供独立复测。"
    )
    (output / "request.txt").write_text(prompt + "\n", encoding="utf-8")
    command = ["codex", "--ask-for-approval", "never", "exec", "--sandbox", "workspace-write",
               "--add-dir", str(agent_runs),
               "--json", "--output-last-message", str(output / "final-reply.txt")]
    if model := os.environ.get("QWEN_E2E_CODEX_MODEL"):
        command += ["--model", model]
    run_logged([*command, "-"], project, output / "codex.jsonl", timeout, prompt.encode("utf-8"))
    # The campaign and final reply must both belong to this fresh invocation.
    plan = json.loads((campaign / "plan.json").read_bytes())
    state = json.loads((campaign / "state.json").read_bytes())
    completed_rounds = len(state["rounds"])
    if (plan["round_mode"] != "exact" or plan["round_limit"] != OPTIMIZATION_ROUNDS
            or completed_rounds != OPTIMIZATION_ROUNDS):
        raise ValueError(
            f"Expected exactly {OPTIMIZATION_ROUNDS} planned and completed optimization rounds; "
            f"found round_mode={plan['round_mode']!r}, round_limit={plan['round_limit']}, "
            f"completed_rounds={completed_rounds}"
        )
    if (not (output / "final-reply.txt").read_text(encoding="utf-8").strip()
            or plan["task_source"] != "project" or Path(plan["working_candidate"]) != project
            or state["state"] != "completed"
            or identity(project, plan["candidate_includes"]) != state["final"]["candidate_sha256"]):
        raise ValueError("The Codex run did not deliver the final source of this project campaign")
    return completed_rounds


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
    pixels = {}
    for seed in seeds:
        with Image.open(output / f"seed-{seed}.png") as image:
            if image.mode != "RGBA" or image.size != (workload["width"], workload["height"]):
                raise ValueError("Unexpected decoded image format")
            pixels[seed] = hashlib.sha256(image.tobytes()).hexdigest()
    identity = {k: receipt[k] for k in ("device", "sample_sigmas", "workload_sha256",
                                         "model_index_sha256")}
    return median(times), pixels, identity


def verify_source(repo, expected_tree):
    if (git(repo, "write-tree").decode().strip() != expected_tree
            or git(repo, "diff", "--name-only", "--", "vllm_omni")
            or git(repo, "ls-files", "--others", "--exclude-standard", "--", "vllm_omni")):
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
        minimum = float(os.environ.get("QWEN_E2E_MIN_GAIN_PCT", "0"))
        if timeout <= 0 or not math.isfinite(minimum) or minimum < 0:
            raise ValueError("Invalid timeout or minimum latency reduction")
        workload = json.loads((CASE / "workload.json").read_bytes())
        baseline, project, candidate = (output / n for n in ("baseline", "optimize", "candidate"))
        for tree in (baseline, project):
            checkout(repo, revision, tree)
        baseline_tree = git(baseline, "write-tree").decode().strip()
        first, reference, identity = sample(baseline, checkpoint, output / "preflight-a",
                                            timeout, workload)
        second, pixels, other = sample(baseline, checkpoint, output / "preflight-b",
                                       timeout, workload)
        if (pixels != reference or identity != other
                or identity["sample_sigmas"] != workload["sample_sigmas"]
                or identity["workload_sha256"] != hashlib.sha256(
                    (CASE / "workload.json").read_bytes()).hexdigest()):
            raise ValueError("Baseline A/A pixels or environment changed before optimization")
        noise = 100 * abs(second - first) / first
        report.update(baseline_revision=revision, environment=identity, aa_ms=[first, second],
                      noise_pct=noise, min_gain_pct=minimum)
        write_json(output / "frozen.json", report)
        report["stage"] = "codex"
        report["completed_optimization_rounds"] = optimize(project, checkpoint, output, timeout)

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
        if git(project, "rev-parse", selected + ":vllm_omni") != git(
                candidate, "rev-parse", rebuilt + ":vllm_omni"):
            report.update(verdict="FAIL", error="Patch does not reconstruct the selected source")
            pytest.fail(report["error"])
        report.update(candidate_tree=rebuilt, patch_sha256=hashlib.sha256(patch).hexdigest())

        report["stage"] = "independent_retest"
        scores = {"baseline": [], "candidate": []}
        failed_seeds = set()
        for i, pair in enumerate(("AB", "BA", "AB"), 1):
            for arm in pair:
                name, tree = ("baseline", baseline) if arm == "A" else ("candidate", candidate)
                expected_tree = baseline_tree if arm == "A" else rebuilt
                verify_source(tree, expected_tree)
                value, actual, runtime = sample(tree, checkpoint, output / f"{i:02}-{name}",
                                                timeout, workload)
                verify_source(tree, expected_tree)
                if runtime != identity or (name == "baseline" and actual != reference):
                    raise ValueError("Independent baseline or measurement environment changed")
                failed_seeds.update(seed for seed in reference if actual[seed] != reference[seed])
                scores[name].append(value)
        before, after = (median(scores[name]) for name in ("baseline", "candidate"))
        gain = 100 * (before - after) / before
        report.update(stage="finished", group_medians_ms=scores, baseline_ms=before,
                      candidate_ms=after, reduction_ms=before - after, reduction_pct=gain,
                      speedup=before / after, quality_passed=len(reference) - len(failed_seeds),
                      quality_total=len(reference), failed_seeds=sorted(failed_seeds))
        if failed_seeds or gain <= 0 or gain < minimum:
            report["verdict"] = "FAIL"
        elif gain > noise:
            report["verdict"] = "PASS"
        assert report["verdict"] == "PASS", report
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        write_json(output / "result.json", report)
        print(json.dumps(report, ensure_ascii=False), flush=True)
