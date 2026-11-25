"""Synthetic campaign and CLI helpers for service-reuse tests."""

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from inferrsi.apps.cli import main
from inferrsi.apps.storage import artifacts
from inferrsi.harness import artifact_primitives
from inferrsi.harness.records import evidence, knowledge_capture
from inferrsi.knowledge import knowledge_operations
from tests.fixtures.diagnosis import diagnosis_args
from tests.fixtures.target_review import calibration, write_review


@pytest.fixture(autouse=True)
def no_fingerprints(monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("This test must not calculate or verify a file fingerprint")

    # Keep imported functions intact; only their defining modules see the guard.
    for module in (
        artifact_primitives, artifacts, evidence, knowledge_capture, knowledge_operations,
    ):
        monkeypatch.setattr(module, "hashlib", SimpleNamespace(sha256=forbidden))
    yield
    assert not calls, "A fingerprint call was attempted, even if execution caught its exception"


def commit(repo, **changes):
    config = {"version": "baseline", "a": 100, "b": 100, "quality": 1}
    config.update(changes)
    (repo / "engine.py").write_text("CONFIG = " + repr(config) + "\n", encoding="utf-8")
    for args in (
        ("add", "engine.py"),
        (
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "Synthetic version",
        ),
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def settings():
    return {
        "schema_version": 1,
        "protocol_id": "synthetic-service-control",
        "conditions": {
            "id": "c0",
            "workload": "synthetic",
            "model": "synthetic",
            "precision": "integers",
            "topology": "one-cpu-process",
            "runtime": "stdlib",
            "timing_scope": "synthetic-value",
            "effective_config": {"mode": "fixture"},
        },
        "commands": {
            name: [
                "{python}",
                "{protocol}/protocol.py",
                name,
                "{candidate}",
                "{service_receipt}",
                "{result}",
            ]
            for name in (
                "precheck",
                "service",
                "ready",
                "warmup",
                "measure",
                "quality",
                "profile",
                "stop",
            )
        },
        "sampling": {
            "stage_timeout_seconds": 8,
            **{
                role: {"repetitions": 2, "warmups": 1}
                for role in ("baseline", "candidate", "final")
            },
        },
        "scenarios": [
            {"id": name, "workload": "synthetic-" + name, "requests": 2, "required_successes": 2}
            for name in ("a", "b")
        ],
        "objectives": [
            {
                "id": name,
                "scenario": name,
                "key": "latency",
                "unit": "ms",
                "domain": {"min": 0, "max": 10000},
                "direction": "minimize",
                "aggregate": "median",
                "threshold_type": "relative_percent",
                "gain": True,
                "gain_threshold": 4,
                "parent_regression_limit": 3,
                "cumulative_regression_limit": 3,
            }
            for name in ("a", "b")
        ],
        "ranking": ["a", "b"],
        "quality": {
            "mode": "absolute",
            "dataset": "synthetic",
            "scorer": "exact-v1",
            "samples": 2,
            "key": "quality",
            "direction": "maximize",
            "threshold": 1,
        },
        "stagnation": {"rounds": 2, "action": "advisory"},
    }


def service_review(root, conditions, revision):
    objectives = settings()["objectives"]
    measurements = {obj["id"]: {**calibration(obj["unit"], obj["direction"]),
                                "metric": obj["key"], "baseline_samples": [100, 100],
                                "attainable_value": 90, "aggregate": obj["aggregate"],
                                "scenario": obj["scenario"]} for obj in objectives}
    return write_review(root.with_suffix(".review.json"),
                        {"conditions": conditions, "baseline_revision": revision}, measurements,
                        {obj["id"]: obj["gain_threshold"] for obj in objectives})


def calibrate_start(campaign):
    revision = subprocess.check_output(
        ["git", "-C", campaign["repo"], "rev-parse", "HEAD"], text=True
    ).strip()
    conditions = json.loads(campaign["config"].read_text())["conditions"]
    return service_review(campaign["root"], conditions, revision)


@pytest.fixture
def campaign(tmp_path, capsys):
    repo, protocol, root = (tmp_path / name for name in ("repo", "protocol", "campaign"))
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    commit(repo)
    protocol.mkdir()
    shutil.copyfile(
        Path(__file__).with_name("service_reuse_protocol.py"), protocol / "protocol.py"
    )
    instructions = tmp_path / "TASK.md"
    instructions.write_text("Synthetic service control; no model claims.")
    configuration = tmp_path / "evaluation.json"
    configuration.write_text(json.dumps(settings()))
    campaign = {"repo": repo, "root": root, "config": configuration, "capsys": capsys}
    campaign["start"] = [
        "campaign",
        "start",
        "--session",
        str(root),
        "--repo",
        str(repo),
        "--include",
        "engine.py",
        "--protocol",
        str(protocol),
        "--instructions",
        str(instructions),
        "--evaluation-mode",
        "service_reuse",
        "--evaluation-config",
        str(configuration),
        "--target-review",
        calibrate_start(campaign),
        "--rounds",
        "8",
        "--max-minutes",
        "10",
        "--evaluation-timeout-seconds",
        "25",
        "--final-reserve-seconds",
        "30",
    ]
    return campaign


def call(campaign, action, *extra, expected=0):
    if action == "refresh-references" and not {"--retry-of", "--target-review"}.intersection(extra):
        conditions = json.loads(Path(extra[extra.index("--conditions") + 1]).read_text())
        root = campaign["root"]
        revision = json.loads((root / "plan.json").read_text())["baseline_revision"]
        extra = (*extra, "--target-review", service_review(root, conditions, revision))
    args = (
        campaign["start"]
        if action == "start"
        else ["campaign", action, "--session", str(campaign["root"]), *map(str, extra)]
    )
    assert main(args) == expected
    return json.loads(campaign["capsys"].readouterr().out)


def diagnose(campaign):
    assert main(diagnosis_args(campaign["root"], "campaign")) == 0
    campaign["capsys"].readouterr()


def begin(campaign):
    result = call(campaign, "start")
    assert result["next_action"] == "campaign_baseline"
    assert not (campaign["root"] / "baseline").exists()
    result = call(campaign, "baseline")
    assert result["best"]["kind"] == "baseline"
    diagnose(campaign)
    return result


def submit(campaign, *, expected=0, retry=None, **changes):
    commit(campaign["repo"], **changes)
    args = ["--candidate", campaign["repo"], "--hypothesis", "Synthetic committed candidate"]
    if retry:
        args += ["--retry-of", retry, "--repair-reason", "Investigated and repaired fixture"]
    return call(campaign, "round", *args, expected=expected)


def rejected(arguments):
    with pytest.raises(SystemExit) as raised:
        main(arguments)
    return raised.value.code
