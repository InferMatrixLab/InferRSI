import json
import sys
from pathlib import Path

import pytest

from examples.qwen38_text import launch


def args(tmp_path):
    workload = tmp_path / "workload.json"
    workload.write_text(json.dumps({"schema_version": 1, "model_id": "Qwen/Qwen3.8-27B",
                                    "cases": [{"id": "one", "prompt": "abc",
                                               "continuation": "def", "max_steps": 1}]}))
    return ["launch", "--repo", str(Path(launch.__file__).resolve().parents[2]),
            "--model-path", str(tmp_path), "--manifest", str(tmp_path / "manifest.json"),
            "--model-revision", "a" * 40, "--workload", str(workload),
            "--output-dir", str(tmp_path / "results"), "--device-model", "Synthetic GPU",
            "--max-nrmse", "0.01", "--min-top1", "0.99", "--rms-floor", "1e-8",
            "--max-minutes", "1", "--repetitions", "1"]


def test_preview_retains_source_and_allocation(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "3")
    monkeypatch.setattr(sys, "argv", args(tmp_path) + ["--dry-run"])
    assert launch.main() == 0
    spec = json.loads(capsys.readouterr().out)
    assert spec["device_ids"] == ["3"]
    assert spec["objective"] == "correctness"
    assert spec["comparison_scope"] == "reference_self_check"
    assert "{run_dir}" in spec["validation_command"]
    assert not (tmp_path / "results").exists()


def test_unrelated_source_cannot_be_snapshotted(tmp_path, monkeypatch):
    argv = args(tmp_path)
    argv[argv.index("--repo") + 1] = str(tmp_path)
    monkeypatch.setattr(sys, "argv", argv + ["--dry-run"])
    with pytest.raises(SystemExit) as exc:
        launch.main()
    assert exc.value.code == 2


def test_execution_requires_slurm(tmp_path, monkeypatch):
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setattr(sys, "argv", args(tmp_path))
    with pytest.raises(SystemExit) as exc:
        launch.main()
    assert exc.value.code == 2


def test_output_cannot_escape_task_root(tmp_path, monkeypatch):
    monkeypatch.setenv("TASK_ROOT", str(tmp_path / "authorized"))
    monkeypatch.setattr(sys, "argv", args(tmp_path) + ["--dry-run"])
    with pytest.raises(SystemExit) as exc:
        launch.main()
    assert exc.value.code == 2
