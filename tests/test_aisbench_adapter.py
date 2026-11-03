"""AISBench service adapter contracts without AISBench, a service or a GPU."""

import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from examples import aisbench_adapter as adapter
from inferrsi.harness.scenarios.external import execute_trial

IDENTITY = dict(
    model_config="service_model",
    dataset_config="example_gen",
    model_abbr="model",
    dataset_abbr="dataset",
)
OPTIONS = [arg for key, value in IDENTITY.items() for arg in ["--" + key.replace("_", "-"), value]]
ROWS = [
    {"id": n, "data_abbr": "dataset", "prediction": "PRIVATE ANSWER", "success": True}
    for n in range(2)
]
PERF = {
    "Total Requests": {"total": 2},
    "Success Requests": {"total": 2},
    "Failed Requests": {"total": 0},
    "Output Token Throughput": {"total": "12.375 token/s"},
}


@pytest.fixture
def invocation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = tmp_path / "trial" / "result.json"
    monkeypatch.setenv("INFERRSI_RESULT_PATH", str(result))
    ref = tmp_path / "reference.json"

    def run(
        mode="validate",
        *,
        score=80,
        report=None,
        rows=ROWS,
        child_code=0,
        emit=True,
        second=False,
        symlink=False,
        reference=None,
        sha=None,
        options=OPTIONS,
    ):
        frozen = {
            "schema": "aisbench-accuracy-reference-v1",
            **IDENTITY,
            "accuracy": 80,
            "max_drop": 0.5,
            "expected_samples": 2,
            **(reference or {}),
        }
        ref.write_text(json.dumps(frozen), encoding="utf-8")
        digest = hashlib.sha256(ref.read_bytes()).hexdigest() if sha is None else sha
        called = []

        def child(argv, cwd, check):
            called.append(argv)
            assert check is False
            assert Path(cwd).is_dir() and Path(cwd).parent == result.parent
            assert argv[:7] == [
                "ais_bench",
                "--models",
                "service_model",
                "--datasets",
                "example_gen",
                "--mode",
                "all" if mode == "validate" else "perf",
            ]
            assert argv[7:] == ["--work-dir", str(result.parent / "aisbench")]
            work = Path(argv[-1])
            root = work / "20261013_111111"
            root.mkdir()
            if second:
                (work / "20261013_111112").mkdir()
            if emit:
                target = (
                    root
                    / ("results" if mode == "validate" else "performances")
                    / "model"
                    / "dataset.json"
                )
                target.parent.mkdir(parents=True)
                data = (
                    report
                    if report is not None
                    else ({"accuracy": score} if mode == "validate" else PERF)
                )
                encoded = data if isinstance(data, bytes) else json.dumps(data).encode()
                if symlink:
                    outside = tmp_path / "outside.json"
                    outside.write_bytes(encoded)
                    target.symlink_to(outside)
                else:
                    target.write_bytes(encoded)
                pred = root / "predictions/model/dataset.jsonl"
                pred.parent.mkdir(parents=True)
                pred.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            return SimpleNamespace(returncode=child_code)

        monkeypatch.setattr(adapter.subprocess, "run", child)
        cmd = [mode, *options]
        if mode == "validate":
            cmd += ["--reference", str(ref), "--reference-sha256", digest]
        code = adapter.main(cmd)
        return code, json.loads(result.read_text(encoding="utf-8")), called

    return run


@pytest.mark.parametrize(
    ("score", "code", "status"),
    [(81, 0, "PASS"), (79.5, 0, "PASS"), (79.49, 1, "FAIL"), (0, 1, "FAIL")],
)
def test_reference_gate(invocation, score, code, status):
    result_code, doc, calls = invocation(score=score)
    assert len(calls) == 1
    assert (result_code, doc["status"]) == (code, status)
    assert doc["metrics"] == {"accuracy": score}
    proof = doc["provenance"]
    assert proof["run_id"] == "20261013_111111"
    assert proof["report"] == "aisbench/20261013_111111/results/model/dataset.json"
    assert proof["sample_count"] == 2 and len(proof["predictions_sha256"]) == 64
    assert proof["child_returncode"] == 0
    assert "PRIVATE ANSWER" not in json.dumps(doc)


def test_native_perf_json_and_stable_metric(invocation):
    code, doc, _ = invocation("perf")
    assert code == 0 and doc["metrics"]["output_tokens_per_second"] == 12.375
    assert doc["provenance"]["report"] == "aisbench/20261013_111111/performances/model/dataset.json"
    assert (
        doc["provenance"]["report_sha256"] == hashlib.sha256(json.dumps(PERF).encode()).hexdigest()
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"emit": False},
        {"second": True},
        {"symlink": True},
        {"report": b"not json"},
        {"report": b'{"details":' + b"[" * 2000 + b"]" * 2000 + b"}"},
        {"report": b'{"accuracy": 40,"accuracy": 70}'},
        {"report": {"accuracy": True}},
        {"report": {"accuracy": 101}},
        {"report": {"accuracy": 10, "error": "failed"}},
        {"rows": ROWS[:-1]},
        {"rows": [ROWS[0], ROWS[0]]},
        {"rows": [ROWS[0], {**ROWS[1], "data_abbr": "another-dataset"}]},
        {"rows": [*ROWS[:1], {**ROWS[1], "success": False}]},
        {"rows": [*ROWS[:1], {k: v for k, v in ROWS[1].items() if k != "success"}]},
        {"rows": [*ROWS[:1], {**ROWS[1], "id": 4}]},
        {"child_code": 1},
        {"child_code": 2},
    ],
)
def test_incomplete_child_evidence_cannot_be_a_regression(invocation, changes):
    code, doc, calls = invocation(score=0, **changes)
    assert len(calls) == 1 and code == 2
    assert doc["status"] == "INCONCLUSIVE" and not doc["metrics"]


@pytest.mark.parametrize(
    "changes",
    [
        {"Failed Requests": {"total": 1}},
        {"Success Requests": {"total": 1}},
        {"Total Requests": {"total": True}},
        {"Output Token Throughput": {"total": "0 token/s"}},
        {"Output Token Throughput": {"total": "2 ms"}},
        {"Output Token Throughput": {"steady": "2 token/s"}},
    ],
)
def test_bad_perf_is_not_a_measurement(invocation, changes):
    code, doc, _ = invocation("perf", report={**PERF, **changes})
    assert code == 2 and doc["status"] == "INCONCLUSIVE" and not doc["metrics"]


@pytest.mark.parametrize(
    "changes",
    [
        {"sha": "0" * 64},
        {"reference": {"dataset_config": "other"}},
        {"reference": {"schema": "other"}},
        {"reference": {"expected_samples": False}},
        {"reference": {"max_drop": -1}},
        {"options": [*OPTIONS, "--model-abbr", "../other"]},
    ],
)
def test_invalid_reference_or_identity_fails_before_launch(invocation, changes):
    code, doc, calls = invocation(**changes)
    assert code == 2 and not calls and doc["status"] == "INCONCLUSIVE"


def test_existing_run_is_never_reused(invocation, tmp_path):
    (tmp_path / "trial/aisbench/20261013_111111/results/model").mkdir(parents=True)
    code, doc, calls = invocation()
    assert code == 2 and not calls and doc["status"] == "INCONCLUSIVE"


def test_explicit_result_and_real_subprocess_failure(tmp_path, monkeypatch):
    monkeypatch.delenv("INFERRSI_RESULT_PATH", raising=False)
    result = tmp_path / "trial/result.json"
    # Python rejects AISBench's argv and exits nonzero.
    argv = ["perf", *OPTIONS, "--ais-bench", sys.executable, "--result", str(result)]
    assert adapter.main(argv) == 2
    raw = result.read_bytes()
    doc = json.loads(raw)
    assert doc["provenance"]["child_returncode"] != 0 and doc["status"] == "INCONCLUSIVE"
    assert adapter.main(argv) == 2 and result.read_bytes() == raw


def test_concurrent_trials_keep_worker_files_out_of_checkout(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    monkeypatch.delenv("INFERRSI_RESULT_PATH", raising=False)
    child = checkout / "ais_bench"
    child.write_text(
        f"#!{sys.executable}\n"
        "import json, sys, time\n"
        "from pathlib import Path\n"
        "arg = lambda name: Path(sys.argv[sys.argv.index(name) + 1])\n"
        "role = arg('--models').name\n"
        "assert arg('--config-dir').parent.name == role\n"
        "assert arg('--mode').name == 'perf'\n"
        "work = arg('--work-dir')\n"
        "assert Path.cwd().parent == work.parent\n"
        "Path('tmp').mkdir()\n"
        "Path('tmp/params.py').touch()\n"
        "(work.parent / 'ready').touch()\n"
        "deadline = time.monotonic() + 5\n"
        "while len(list(work.parent.parent.glob('*/ready'))) < 2:\n"
        "    assert time.monotonic() < deadline\n"
        "    time.sleep(0.01)\n"
        "report = work / '20261013_111111/performances/model/dataset.json'\n"
        "report.parent.mkdir(parents=True)\n"
        f"data = {PERF!r}\n"
        "if role == 'candidate':\n"
        "    data['Output Token Throughput']['total'] = '15 token/s'\n"
        "report.write_text(json.dumps(data))\n",
        encoding="utf-8",
    )
    child.chmod(0o700)

    def run(name):
        repo = checkout / name
        (repo / "configs").mkdir(parents=True)
        trial = tmp_path / "trials" / name
        command = (
            sys.executable, adapter.__file__, "perf", *OPTIONS,
            "--model-config", name, "--ais-bench", str(child),
        )
        record = execute_trial(
            command, repo, trial, time.monotonic() + 20, "metrics.output_tokens_per_second"
        )
        assert record["status"] == "completed", (trial / "stderr.log").read_text()
        assert record["metric"] == (15 if name == "candidate" else 12.375)
        result = Path(record["result_path"])
        proof = json.loads(result.read_text())["provenance"]
        assert proof["argv"][0] == str(child)
        assert not (result.parent / proof["child_cwd"]).exists()
        assert not (repo / "tmp").exists()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, ["baseline", "candidate"]))
    assert not (checkout / "tmp").exists()
