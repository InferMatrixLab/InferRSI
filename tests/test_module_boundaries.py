"""Prove that extension adapters reuse the real scheduler and process executor."""

import ast
import json
import subprocess
import sys
from functools import partial
from pathlib import Path
from unittest.mock import patch

import pytest

from inferrsi.harness.runner import run_experiment
from inferrsi.harness.scenarios.external import execute_trial
from inferrsi.infra.platforms import PLATFORM_PROBES, inspect_device
from inferrsi.infra.platforms.cuda import qualify_devices
from inferrsi.model.protocols.metrics import read_metric
from inferrsi.runspec import RunSpec


def test_new_scenario_target_and_backend_share_abba_and_verdict(tmp_path):
    repo = tmp_path / "new-engine"
    repo.mkdir()
    # A non-Git target adapter supplies the same source-integrity contract.
    snapshots = []

    def snapshot(path, exclude):
        snapshots.append((path, exclude))
        return {"available": True, "snapshot_hash": "fixture-source", "path": str(path)}

    def command(value):
        return (
            sys.executable,
            "-c",
            "import json,sys; open(sys.argv[1], 'w').write(json.dumps({'duration': sys.argv[2]}))",
            "{result}",
            str(value),
        )

    def metric_reader(document, key):
        # Convert a new engine's schema and units before the common metric check.
        return read_metric({"metrics": {"latency_ms": float(document["duration"]) * 1000}}, key)

    def probe(**kwargs):
        return {"status": "available", "selection_verified": True, "test_fixture": True}

    with patch.dict(PLATFORM_PROBES, {"fixture_backend": probe}):
        device = inspect_device(
            "fixture_backend", device_ids=("test-device",), device_model="fixture", command=None
        )
    spec = RunSpec(
        repo=str(repo),
        repo_type="fixture_engine",
        backend="fixture_backend",
        scenario="new_model.custom_metrics",
        baseline_command=command(0.1),
        candidate_command=command(0.08),
        validation_command=(sys.executable, "-c", "print('fixture validation')"),
        repetitions=2,
        output_dir=str(tmp_path / "runs"),
        max_minutes=1,
    )
    path = run_experiment(
        spec,
        {"device": device},
        execute=partial(execute_trial, metric_reader=metric_reader),
        snapshot=snapshot,
    )
    result = json.loads((path / "evaluation.json").read_text())
    assert result["verdict"] == "PASS"  # Synthetic contract data, not a hardware result.
    assert result["improvement_pct"] == pytest.approx(20)
    assert result["source_integrity"]["command_checks"] == 5
    events = [json.loads(line) for line in (path / "events.jsonl").read_text().splitlines()]
    assert [e["side"] for e in events if e["phase"] == "measurement"] == [
        "baseline",
        "candidate",
        "candidate",
        "baseline",
    ]
    assert len(snapshots) == 14
    assert (path / "report.html").is_file()
    for side in ("baseline", "candidate"):
        for trial in (1, 2):
            execution = json.loads((path / side / f"trial-{trial:03d}/execution.json").read_text())
            assert execution["pid"] > 0
            assert execution["returncode"] == 0
            assert execution["metric_error"] is None


def test_cuda_qualification_accepts_campaign_supplied_count_and_sku(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "GPU-fixture")
    device = subprocess.CompletedProcess([], 0, "0, GPU-fixture, NVIDIA H100 SXM, driver\n", "")
    empty = subprocess.CompletedProcess([], 0, "", "")
    with patch("inferrsi.infra.platforms.cuda.subprocess.run", side_effect=[device, empty]):
        selected = qualify_devices(count=1, device_model="H100")
    assert selected[0]["uuid"] == "GPU-fixture"
    busy = subprocess.CompletedProcess([], 0, "GPU-fixture, 123, other-work\n", "")
    with patch("inferrsi.infra.platforms.cuda.subprocess.run", side_effect=[device, busy]):
        with pytest.raises(ValueError, match="already has a compute process"):
            qualify_devices(count=1, device_model="H100")


def test_shared_layers_do_not_import_campaigns_or_reverse_dependencies():
    root = Path(__file__).resolve().parents[1] / "src/inferrsi"
    for plane in ("infra", "model", "harness"):
        for path in (root / plane).rglob("*.py"):
            package = ".".join(("inferrsi", *path.relative_to(root).parts[:-1]))
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        parts = package.split(".")
                        prefix = parts[: len(parts) - node.level + 1]
                        names = [".".join(prefix + ([node.module] if node.module else []))]
                    else:
                        names = [node.module or ""]
                else:
                    continue
                for name in names:
                    assert "examples" not in name.split("."), (path, name)
                    assert "ltx25" not in name and "qwen21" not in name, (path, name)
                    if plane == "infra":
                        assert not name.startswith(("inferrsi.harness", "inferrsi.model")), (
                            path,
                            name,
                        )
                    if plane == "model":
                        assert not name.startswith("inferrsi.harness"), (path, name)


def test_control_imports_need_no_inference_or_image_dependencies():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import inferrsi.cli; "
            "import inferrsi.model.validators.image; "
            "assert not {'torch', 'vllm', 'numpy', 'PIL', 'skimage'}.intersection(sys.modules)",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
