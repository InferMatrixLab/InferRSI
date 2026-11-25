"""Control-level finals and protocol identity for the Qwen pilot, without device access."""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from inferrsi.benchmark.registry import task_resources

BUNDLE = Path(__file__).resolve().parents[2] / "evidence/qwen-vats-gvo-910b1-20261124"


def module(relative):
    spec = importlib.util.spec_from_file_location("diagnostic", BUNDLE / relative)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.mark.parametrize("verdict,promoted", [("INCONCLUSIVE", False), ("PASS", False)])
def test_inner_pass_cannot_publish_failed_promotion(tmp_path, monkeypatch, verdict, promoted):
    driver = module("plan/run.py")

    class Evaluator:
        def __init__(self, task, frozen, *, arguments):
            self.frozen = frozen
            self.identity = "cpu-test"
            frozen.mkdir()
            shutil.copyfile(task_resources(task) / "baseline.py", frozen / "baseline.py")

        def evaluate(self, candidate, check, output, deadline):
            output.mkdir(parents=True)
            return {"verdict": "PASS", "objective": 1.25, "cleanup_verified": True}

    original = driver.finalize

    def refused(*args, **kwargs):
        final = original(*args, **kwargs)
        return {**final, "verdict": verdict, "promoted": promoted}

    monkeypatch.setattr(driver, "EngineEvaluator", Evaluator)
    monkeypatch.setattr(driver, "finalize", refused)
    output = tmp_path / "trial"
    with pytest.raises(ValueError, match="final"):
        driver.run(output)
    summary = json.loads((output / "summary.json").read_text())
    first, rejected, *unrun = summary["blocks"]
    assert first["status"] == "complete"
    assert rejected["status"] == "incomplete" and rejected["final_score"] is None
    assert rejected["final_verdict"] == verdict and rejected["promoted"] is False
    assert all(row["status"] == "not_run" for row in unrun)
    assert "trained_over_frozen" not in summary


def test_protocol_identity_checked_before_loading(tmp_path, monkeypatch):
    checker = module("validator/check.py")
    task = tmp_path / "task"
    shutil.copytree(task_resources("qwen21-denoise-npu"), task)
    plan = tmp_path / "plan"
    shutil.copytree(checker.PLAN, plan)
    spec = json.loads((plan / "runspec.json").read_text())
    spec["packaged_task_sha256"] = {
        name: checker.sha(task / name) for name in spec["packaged_task_sha256"]
    }
    (plan / "runspec.json").write_text(json.dumps(spec))
    (task / "optimization.py").write_text("this is deliberately invalid Python source.")
    monkeypatch.setattr(checker, "PLAN", plan)
    monkeypatch.setattr(checker, "task_resources", lambda _: task)
    with pytest.raises(ValueError, match="optimization.py"):
        checker.main(tmp_path / "trial", tmp_path / "failed")


@pytest.mark.parametrize(
    "fault", ["verdict", "promotion", "selection", "receipt", "source", "rule", "operation-rule"]
)
def test_offline_checker_requires_bound_durable_promotion(tmp_path, fault):
    from inferrsi.harness import candidates

    checker = module("validator/check.py")
    candidate_dir = tmp_path / "winner"
    candidate_dir.mkdir()
    source = candidate_dir / "candidate.py"
    source.write_bytes(b"selected candidate")
    node = {"candidate_id": "winner", "artifact_digest": candidates.identity(candidate_dir)}
    receipt = {"verdict": "PASS", "cleanup_verified": True, "objective": 1.2}
    final = {"candidate": "winner", "verdict": "PASS", "promoted": True, "results": [receipt]}
    binding = {
        "candidate": node,
        "deployment_search": "frozen-101",
        "acceptance": {"version": 1, "minimum_objective": None},
    }
    op = {
        "category": "final",
        "status": "settled",
        "binding": binding | {"check": "evaluation"},
        "receipt": receipt,
    }
    state = {"stable": node, "searches": {"frozen-101": {"selected": "winner"}}}
    doc = {
        "final_result": final,
        "final_claim": {"scope": "frozen-101", "binding": binding},
        "state": state,
        "operations": {"final-1": op},
    }

    def replay():
        return checker.promoted_final(doc, "frozen-101", tmp_path, require_acceptance=True)

    assert replay() == (receipt, checker.sha(source))
    if fault == "verdict":
        final["verdict"] = "INCONCLUSIVE"
    elif fault == "promotion":
        final["promoted"] = False
    elif fault == "selection":
        state["searches"]["frozen-101"]["selected"] = "root"
    elif fault == "receipt":
        op["receipt"] = {**receipt, "objective": 1.3}
    elif fault == "rule":
        binding.pop("acceptance")
    elif fault == "operation-rule":
        op["binding"]["acceptance"] = {"version": 1, "minimum_objective": 0}
    else:
        source.write_bytes(b"other candidate")
    with pytest.raises(ValueError, match="frozen-101"):
        replay()
