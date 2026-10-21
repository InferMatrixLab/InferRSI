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


def test_native_preview_binds_distinct_control_and_candidate(tmp_path, monkeypatch, capsys):
    engine = tmp_path / "engine"
    engine.mkdir()
    monkeypatch.setattr(sys, "argv", args(tmp_path) + [
        "--qualification-scope", "native_text_smoke", "--candidate-repo", str(engine), "--dry-run",
    ])
    assert launch.main() == 0
    spec = json.loads(capsys.readouterr().out)
    assert spec["candidate_repo"] == str(engine)
    assert spec["comparison_scope"] == "native_text_smoke"
    assert spec["baseline_command"][-4:] == ["--mode", "full", "--qualification-scope",
                                            "native_text_smoke"]
    assert spec["candidate_command"][1].endswith("native_trial.py")
    assert "--mode" not in spec["candidate_command"]
    assert spec["candidate_command"][-2:] == ["--engine-repo", str(engine)]


@pytest.mark.parametrize("extra", [
    ["--qualification-scope", "native_text_smoke"],
    ["--candidate-repo", "."],
])
def test_native_role_requires_explicit_consistent_scope(tmp_path, monkeypatch, extra):
    monkeypatch.setattr(sys, "argv", args(tmp_path) + extra + ["--dry-run"])
    with pytest.raises(SystemExit) as exc:
        launch.main()
    assert exc.value.code == 2


def test_fp8_preview_propagates_explicit_profile_and_frozen_kernel(tmp_path, monkeypatch, capsys):
    from examples.qwen38_text.profiles import FP8_MODEL_ID, precision

    argv = args(tmp_path)
    path = tmp_path / "workload.json"
    workload = json.loads(path.read_text())
    workload.update(model_id=FP8_MODEL_ID, precision=precision(FP8_MODEL_ID))
    path.write_text(json.dumps(workload))
    argv += ["--model-id", FP8_MODEL_ID, "--fp8-kernel-revision", "b" * 40,
             "--fp8-kernel-sha256", "c" * 64, "--dry-run"]
    monkeypatch.setattr(sys, "argv", argv)
    assert launch.main() == 0
    spec = json.loads(capsys.readouterr().out)
    assert spec["model"] == FP8_MODEL_ID
    for key in ("baseline_command", "candidate_command", "validation_command"):
        assert "--model-id" in spec[key] and FP8_MODEL_ID in spec[key]
        assert "--fp8-kernel-revision" in spec[key] and "b" * 40 in spec[key]
    monkeypatch.setattr(sys, "argv", argv[:-5] + ["--dry-run"])
    with pytest.raises(SystemExit):
        launch.main()
