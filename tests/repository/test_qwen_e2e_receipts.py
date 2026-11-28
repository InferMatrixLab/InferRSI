import hashlib
import json
import shutil
from decimal import Decimal
from types import SimpleNamespace

import pytest

from e2e.qwen_image import test_user_journey as journey
from e2e.qwen_image.sampling_trace import SamplingTraceExtension


def scheduler_trace(timesteps):
    class Scheduler:
        def __init__(self):
            self.step_index = 0
            self.sigmas = [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.0]

        def step(self, model_output, timestep):
            self.step_index += 1

    scheduler = Scheduler()
    worker = SamplingTraceExtension()
    worker.model_runner = SimpleNamespace(pipeline=SimpleNamespace(scheduler=scheduler))
    step = Scheduler.step
    worker.begin_qwen_e2e_trace()
    for timestep in timesteps:
        scheduler.step(None, timestep)
    trace = worker.end_qwen_e2e_trace()
    assert Scheduler.step is step
    return trace


@pytest.mark.parametrize(("gain", "noise", "expected"), [
    ("10", 0.2, "FAIL"),
    ("9.99999", 0.2, "FAIL"),
    ("10.1001", 0.2, "PASS"),
    ("11", 14, "INCONCLUSIVE"),
])
def test_strict_gain_and_frozen_noise(gain, noise, expected):
    assert journey.performance_verdict(Decimal(gain), 10, noise, set()) == expected


@pytest.fixture
def e2e_case(tmp_path, monkeypatch):
    repo = tmp_path / "repository"
    pkg = repo / "vllm_omni"
    pkg.mkdir(parents=True)
    (pkg / "model.py").write_text("BASELINE = True\n", encoding="utf-8")
    (repo / ".gitignore").write_text("vllm_omni/helper.py\n", encoding="utf-8")
    journey.git(repo, "init", "--quiet")
    journey.git(repo, "add", ".")
    journey.git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "commit", "--quiet", "-m", "Synthetic baseline")
    revision = journey.git(repo, "rev-parse", "HEAD").decode().strip()
    monkeypatch.setenv("QWEN_E2E_MIN_GAIN_PCT", "10")
    monkeypatch.setenv("QWEN_E2E_REPO", str(repo))
    monkeypatch.setenv("QWEN_E2E_REVISION", revision)
    monkeypatch.setenv("QWEN_E2E_CHECKPOINT", str(repo))
    monkeypatch.setenv("QWEN_E2E_RESULTS", str(tmp_path / "results"))
    monkeypatch.setattr(journey, "CASE_BASELINE_REVISION", revision)
    return repo


def test_rejects_another_valid_git_revision_before_checkout(tmp_path, monkeypatch, e2e_case):
    repo = e2e_case
    journey.git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "commit", "--quiet", "--allow-empty", "-m", "Different valid revision")
    wrong_revision = journey.git(repo, "rev-parse", "HEAD").decode().strip()
    assert wrong_revision != journey.CASE_BASELINE_REVISION
    monkeypatch.setenv("QWEN_E2E_REVISION", wrong_revision)

    def unexpected_checkout(*args):
        pytest.fail("A different valid baseline must be rejected before checkout and measurement")

    monkeypatch.setattr(journey, "checkout", unexpected_checkout)
    with pytest.raises(ValueError, match="must equal the pinned baseline"):
        journey.test_codex_optimizes_qwen_image_on_a2(tmp_path)
    receipt, = (tmp_path / "results").glob("*/result.json")
    report = json.loads(receipt.read_bytes())
    assert report["verdict"] == "INCONCLUSIVE"
    assert report["stage"] == "preflight"


def test_floor_rejects_lower_configuration(monkeypatch):
    monkeypatch.setenv("QWEN_E2E_MIN_GAIN_PCT", "1")
    with pytest.raises(ValueError, match="gain floor of at least 10%"):
        journey.read_minimum_gain()


@pytest.mark.parametrize("defect", ["ignored_file", "shortened_grid", "different_timestep", "none"])
def test_retest_binds_measured_source_and_grid(tmp_path, monkeypatch, e2e_case, defect):
    case = tmp_path / "case"
    case.mkdir()
    workload = {"requests": [{"seed": 42}], "warmups": [{"seed": 30}],
                "width": 2, "height": 2, "sample_sigmas": [1.0] * 8}
    workload_file = case / "workload.json"
    journey.write_json(workload_file, workload)
    workload_sha = hashlib.sha256(workload_file.read_bytes()).hexdigest()
    calls = []

    def optimize(project, checkpoint, output, timeout):
        pkg = project / "vllm_omni"
        (pkg / "model.py").write_text("BASELINE = False\n", encoding="utf-8")
        if defect == "ignored_file":
            (pkg / "helper.py").write_text("REQUIRED = True\n", encoding="utf-8")
        return [{"candidate_sha256": journey.source_digest(project, ["vllm_omni"])}] * 3

    def measure(source, checkpoint, output, timeout):
        calls.append(source.name)
        output.mkdir()
        timesteps = list(range(8, 0, -1))
        if source.name == "candidate":
            if defect == "shortened_grid":
                timesteps.pop()
            elif defect == "different_timestep":
                timesteps[-1] = 0
        observed = scheduler_trace(timesteps)
        journey.write_json(output / "result.json", {
            "device": "fixture", "sample_sigmas": workload["sample_sigmas"],
            "model_index_sha256": "fixture", "workload_sha256": workload_sha,
            "seeds": [42], "latencies_ms": [80 if source.name == "candidate" else 100],
            "warmup_ms": [100], "sampling_grid": {"30": observed, "42": observed},
        })
        (output / "seed-42.png").write_bytes(bytes((1, 2, 3, 255)) * 4)

    def pixel_digest(path, width, height):
        pixels = path.read_bytes()
        assert len(pixels) == width * height * 4
        return hashlib.sha256(pixels).hexdigest()

    monkeypatch.setattr(journey, "pixel_digest", pixel_digest)
    monkeypatch.setattr(journey, "CASE", case)
    monkeypatch.setattr(journey, "optimize", optimize)
    monkeypatch.setattr(journey, "measure", measure)
    if defect == "ignored_file":
        with pytest.raises(pytest.fail.Exception, match="third measured snapshot"):
            journey.test_codex_optimizes_qwen_image_on_a2(tmp_path)
        assert calls == ["baseline", "baseline"]
    elif defect == "none":
        journey.test_codex_optimizes_qwen_image_on_a2(tmp_path)
        assert calls.count("candidate") == 3
    else:
        with pytest.raises(ValueError, match="effective sampling grid"):
            journey.test_codex_optimizes_qwen_image_on_a2(tmp_path)
        assert calls[-1] == "candidate"


@pytest.mark.parametrize("repeat_candidate", [False, True], ids=["distinct", "repeated"])
def test_optimize_counts_distinct_cumulative_snapshots(tmp_path, monkeypatch, repeat_candidate):
    project = tmp_path / "project"
    source = project / "vllm_omni" / "model.py"
    source.parent.mkdir(parents=True)
    source.write_text("VERSION = 0\n", encoding="utf-8")
    output = tmp_path / "receipts"
    output.mkdir()
    sources = ["vllm_omni"]

    def write_campaigns(*args):
        (output / "final-reply.txt").write_text("Three rounds completed.\n", encoding="utf-8")
        for number in range(1, 4):
            campaign = output / "agent-runs" / f"loop-{number:02d}"
            baseline = campaign / "frozen/baseline"
            shutil.copytree(project, baseline)
            version = 1 if repeat_candidate else number
            source.write_text(f"VERSION = {version}\n", encoding="utf-8")
            snapshot = campaign / "round-01/candidate"
            shutil.copytree(project, snapshot)
            journey.write_json(campaign / "plan.json", {
                "task_source": "project", "working_candidate": str(project),
                "round_mode": "exact", "round_limit": 1, "candidate_includes": sources,
                "baseline_path": "frozen/baseline", "candidate_name": "candidate",
                "baseline_sha256": journey.source_digest(baseline, sources),
            })
            journey.write_json(campaign / "state.json", {
                "state": "completed", "pending": None, "rounds": [{
                    "path": "round-01",
                    "candidate_sha256": journey.source_digest(snapshot, sources),
                    "assessment": {"status": "completed", "quality_passed": True,
                                   "metrics": {"baseline": 100, "candidate": 90}},
                }],
            })

    monkeypatch.setattr(journey, "run_logged", write_campaigns)
    if repeat_candidate:
        with pytest.raises(ValueError, match="Loop 2 did not deliver a new measured snapshot"):
            journey.optimize(project, tmp_path, output, timeout=1)
    else:
        assert len(journey.optimize(project, tmp_path, output, timeout=1)) == 3


def test_optimize_reports_missing_round_receipts(tmp_path, monkeypatch):
    project = tmp_path / "project"
    package = project / "vllm_omni"
    package.mkdir(parents=True)
    (package / "model.py").write_text("BASELINE = True\n", encoding="utf-8")
    output = tmp_path / "receipts"
    output.mkdir()

    def blocked_launch(*args):
        (output / "final-reply.txt").write_text("Campaign launch requires approval.\n",
                                                encoding="utf-8")

    monkeypatch.setattr(journey, "run_logged", blocked_launch)
    with pytest.raises(ValueError, match="Loop 1 did not produce campaign receipts"):
        journey.optimize(project, tmp_path, output, timeout=1)
