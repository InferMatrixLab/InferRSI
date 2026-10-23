import importlib.util
import json
import os
import shutil
import subprocess
import sys

import pytest

from inferrsi.infra.artifacts import write_json
from inferrsi.knowledge_operations import KnowledgeReader, RevisionConflict
from tests.fixtures.skill_eval_compare_support import (
    ROOT,
    FixedOutputClient,
    configuration,
    git,
)
from tools import skill_eval_compare as compare
from tools import skill_eval_pilot


@pytest.mark.parametrize("mode", ["addition", "update"])
def test_real_snapshots_isolated_inputs_and_pair_outcomes(tmp_path, mode):
    config, repo = configuration(tmp_path, mode, ids=("fix", "regression", "same", "wrong",
                                                    "error", "discovery"), repeats=1)
    output = tmp_path / "run"
    authorization = compare.prepare(config, repo, output)
    plan = compare.load_plan(output)
    assert plan["same_bundle"] is False
    assert any("exam.txt" in name for name in plan["source_changes"])
    candidate = output / "plan/bundles/candidate"
    assert (candidate / "selected/SKILL.md").read_text(encoding="utf-8").endswith("New body\n")
    assert (candidate / "selected/resource.txt").read_bytes() == b"new resource"
    assert (candidate / "shared/notes.md").read_bytes() == b"new dependency"
    if mode == "addition":
        assert plan["arms"]["baseline"]["bundle"] is None
        assert not (output / "plan/bundles/baseline").exists()
    else:
        baseline = output / "plan/bundles/baseline"
        assert (baseline / "selected/SKILL.md").read_text(encoding="utf-8").endswith("Old body\n")
        assert (baseline / "selected/resource.txt").read_bytes() == b"old resource"
        assert (baseline / "shared/notes.md").read_bytes() == b"old dependency"
        assert plan["arms"]["baseline"]["bundle"]["dependencies"] != (
            plan["arms"]["candidate"]["bundle"]["dependencies"])
    modes = {("fix", "baseline"): "incorrect", ("regression", "candidate"): "incorrect",
             ("wrong", "baseline"): "incorrect", ("wrong", "candidate"): "incorrect",
             ("error", "candidate"): "invalid_json"}
    client = FixedOutputClient(tmp_path, modes)
    result = compare.execute(output, authorization, client=client)
    assert result["counts"] == {"fix": 1, "regression": 1, "unchanged_correct": 1,
                                "unchanged_incorrect": 1, "missing_pair": 0, "inconclusive": 1}
    assert len(result["discovery"]) == 2
    assert result["conditions"]["candidate"]["expected_trials"] == 5
    assert result["discovery_conditions"]["candidate"]["expected_trials"] == 1
    assert len(client.calls) == 12
    assert len({call["workspace"] for call in client.calls}) == 12
    assert all(not call["workspace"].exists() for call in client.calls)
    assert [call["role"] for call in client.calls[:4]] == [
        "baseline", "candidate", "candidate", "baseline"]
    for index in range(0, len(client.calls), 2):
        left, right = client.calls[index:index + 2]
        assert left["inputs"]["task.json"] == right["inputs"]["task.json"]
        assert left["schema_sha256"] == right["schema_sha256"]
    for call in client.calls:
        assert not any("expected-answer" in name or ".git" in name for name in call["inputs"])
        if mode == "addition" and call["role"] == "baseline":
            assert set(call["inputs"]) == {"task.json"}
            assert "selected" not in call["prompt"]
        if call["case_id"] == "discovery":
            assert "Use the assigned skill" not in call["prompt"]
            if call["role"] == "candidate":
                assert ".agents/skills/selected/SKILL.md" in call["inputs"]
    # The wrong candidate is independently judged by the retained audit verifier.
    regression = next(p for p in result["pairs"] if p["case_id"] == "regression")
    assert regression["candidate"]["checks"]["passed"] is False
    assert any(value is False for value in regression["candidate"]["checks"]["assertions"].values())
    assert result["conditions"]["candidate"]["evaluation_errors"] == 1
    saved = (output / "report.json").read_bytes(), (output / "report.md").read_bytes()
    calls = len(client.calls)
    repo.rename(tmp_path / "source-unavailable")
    compare.report(output)
    assert len(client.calls) == calls
    assert saved == ((output / "report.json").read_bytes(), (output / "report.md").read_bytes())
    assert str(tmp_path) not in (output / "report.json").read_text(encoding="utf-8")
    for pair in result["pairs"]:
        for role in compare.ROLES:
            for name in pair[role]["evidence"].values():
                assert (output / name).is_file()
    with pytest.raises(ValueError, match="fresh results"):
        compare.execute(output, authorization, client=client)


def test_budget_stops_leave_missing_sides_and_unknown_usage(tmp_path):
    config, repo = configuration(tmp_path, ids=("one",), repeats=2, token_stop_new_trials=1)
    output = tmp_path / "run"
    authorization = compare.prepare(config, repo, output)
    client = FixedOutputClient(tmp_path, {("one", "baseline"): "partial_usage"})
    result = compare.execute(output, authorization, client=client)
    assert len(client.calls) == 1
    assert result["status"]["stop_reason"] == "token_budget"
    assert result["status"]["observed_tokens"] == 17
    assert result["counts"]["missing_pair"] == 2
    assert result["counts"]["fix"] == result["counts"]["regression"] == 0
    assert result["conditions"]["baseline"]["input_tokens"] is None
    assert result["conditions"]["baseline"]["output_tokens"] is None
    assert result["conditions"]["candidate"]["cost"] is None
    assert result["pairs"][0]["baseline"]["output"] is not None
    assert result["pairs"][0]["candidate"]["missing"] is True
    assert result["pairs"][1]["baseline"]["missing"] is True


@pytest.mark.parametrize("failure,error", [("timeout", "agent_timeout"),
    ("nonzero", "agent_failed"), ("missing_output", "missing_output"),
    ("invalid_json", "invalid_output_json"), ("invalid_utf8", "invalid_output_json"),
    ("markdown_fence", "invalid_output_json"),
    ("invalid_trace", "agent_trace_error")])
def test_client_errors_cannot_be_fixes_or_regressions(tmp_path, failure, error):
    config, repo = configuration(tmp_path, ids=("one",))
    output = tmp_path / "run"
    authorization = compare.prepare(config, repo, output)
    client = FixedOutputClient(tmp_path, {("one", "candidate"): failure})
    result = compare.execute(output, authorization, client=client)
    trial = result["pairs"][0]["candidate"]
    assert trial["verdict"] == "INCONCLUSIVE" and trial["evaluation_error"] == error
    assert result["counts"]["inconclusive"] == 1
    assert result["counts"]["fix"] == result["counts"]["regression"] == 0
    assert result["conditions"]["candidate"]["evaluation_errors"] == 1
    persisted = json.loads((output / "results/one-candidate-1/result.json").read_text())
    assert persisted["evaluation_error"] == error
    if failure == "invalid_utf8":
        assert trial["output"] == "\\xff\\xfe"
        assert compare.report(output)["pairs"][0]["candidate"]["output"] == "\\xff\\xfe"
        assert (output / "results/one-candidate-1/answer.json").read_bytes() == b"\xff\xfe"
    if failure == "markdown_fence":
        rendered = (output / "report.md").read_text(encoding="utf-8")
        assert "\n`````````text\n" + trial["output"] + "\n`````````\n" in rendered
        assert "\n````text\n" + trial["output"] not in rendered


@pytest.mark.parametrize("fault", ["exception", "wrong_exit", "invalid_json"])
def test_grader_errors_and_interrupted_attempt_are_retained(tmp_path, fault):
    config, repo = configuration(tmp_path, ids=("one",))
    raw = json.loads(config.read_text())
    # Freeze the test fault in the grader rather than model-visible case data.
    grader = tmp_path / "faulty.py"
    source = (ROOT / "tests/fixtures/skill_eval_faulty_verifier.py").read_text(encoding="utf-8")
    grader.write_text(source.replace('task["verifier_fault"]', repr(fault)), encoding="utf-8")
    raw["grader"] = grader.name
    write_json(config, raw)
    output = tmp_path / "run"
    authorization = compare.prepare(config, repo, output)
    result = compare.execute(output, authorization, client=FixedOutputClient(tmp_path))
    assert result["counts"]["inconclusive"] == 1
    assert result["conditions"]["baseline"]["evaluation_errors"] == 1
    trial_path = output / "results/one-candidate-1/result.json"
    trial_path.unlink()
    result = compare.report(output)
    assert result["pairs"][0]["candidate"]["evaluation_error"] == "interrupted_attempt"
    assert result["counts"]["inconclusive"] == 1
    assert result["conditions"]["candidate"]["evaluation_errors"] == 1
    assert not trial_path.exists()


def test_snapshot_revision_and_modified_frozen_resources_are_rejected(tmp_path):
    config, repo = configuration(tmp_path, ids=("one",))
    raw = json.loads(config.read_text())
    raw["snapshots"]["candidate"]["bundle_revision"] = "sha256:" + "0" * 64
    write_json(config, raw)
    with pytest.raises(RevisionConflict):
        compare.prepare(config, repo, tmp_path / "mismatch")
    raw["snapshots"]["candidate"].pop("bundle_revision")
    write_json(config, raw)
    output = tmp_path / "run"
    authorization = compare.prepare(config, repo, output)
    with pytest.raises(ValueError, match="exact plan"):
        compare.execute(output, "0" * 64)
    dependency = output / "plan/bundles/candidate/shared/notes.md"
    dependency.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="Frozen input changed"):
        compare.execute(output, authorization)
    assert not (output / "results/start.json").exists()


@pytest.mark.parametrize("field", ["plan/tasks.json", "plan/schema.json", "validator/verify.py"])
def test_exam_is_frozen_for_both_arms(tmp_path, field):
    config, repo = configuration(tmp_path, ids=("one",))
    output = tmp_path / "run"
    compare.prepare(config, repo, output)
    (output / field).write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="Frozen input changed"):
        compare.report(output)


def test_dependency_only_snapshot_changes_bundle_revision(tmp_path):
    config, repo = configuration(tmp_path, ids=("one",))
    original = KnowledgeReader(skill_root=repo / "library").read("checkout:selected")
    (repo / "library/shared/notes.md").write_text("dependency only", encoding="utf-8")
    current = KnowledgeReader(skill_root=repo / "library").read("checkout:selected")
    assert current.content["selected/SKILL.md"] == original.content["selected/SKILL.md"]
    assert current.revision != original.revision


def test_repeat_identity_and_balanced_schedule():
    tasks = [{"id": "one", "split": "holdout"}, {"id": "two", "split": "holdout"}]
    schedule = compare.build_schedule(tasks, 2)
    assert [(s["task_id"], s["repeat"], s["condition"]) for s in schedule] == [
        ("one", 1, "baseline"), ("one", 1, "candidate"),
        ("one", 2, "candidate"), ("one", 2, "baseline"),
        ("two", 1, "baseline"), ("two", 1, "candidate"),
        ("two", 2, "candidate"), ("two", 2, "baseline"),
    ]


def test_supported_input_shape_accepts_existing_pilot_cases():
    for task in skill_eval_pilot.fixtures():
        compare.validate_input(task, compare.CASE_INPUT)


def test_prepare_and_report_cli_are_model_free(tmp_path):
    config, repo = configuration(tmp_path, "addition", ids=("one",))
    output = tmp_path / "run"
    prefix = [sys.executable, "-m", "tools.skill_eval_compare"]
    # Match pytest's source path in child processes without requiring an editable install.
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    subprocess.run([*prefix, "prepare", "--config", str(config), "--repo", str(repo),
                    "--output", str(output)], cwd=ROOT, env=environment,
                   check=True, capture_output=True)
    subprocess.run([*prefix, "report", "--output", str(output)], cwd=ROOT,
                   env=environment, check=True, capture_output=True)
    assert json.loads((output / "report.json").read_text())["counts"]["missing_pair"] == 1
    assert not (output / "results/start.json").exists()
    denied = subprocess.run([*prefix, "execute", "--output", str(output)], cwd=ROOT,
                            env=environment, capture_output=True)
    assert denied.returncode != 0 and b"--authorize" in denied.stderr


def test_invalid_configs_fail_before_creating_outputs(tmp_path):
    config, repo = configuration(tmp_path, ids=("one",))
    raw = json.loads(config.read_text())
    raw["limits"]["max_task_calls"] = 1
    write_json(config, raw)
    with pytest.raises(ValueError, match="max_task_calls"):
        compare.prepare(config, repo, tmp_path / "too-many")
    assert not (tmp_path / "too-many").exists()
    raw["limits"]["max_task_calls"] = 2
    raw["snapshots"]["candidate"]["git_revision"] = "main"
    write_json(config, raw)
    with pytest.raises(ValueError, match="immutable"):
        compare.prepare(config, repo, tmp_path / "mutable")
    assert not (tmp_path / "mutable").exists()


def test_retained_answer_integrity_changes_invalidate_positive_pairs(tmp_path):
    config, repo = configuration(tmp_path, ids=("fix", "same"))
    output = tmp_path / "run"
    authorization = compare.prepare(config, repo, output)
    client = FixedOutputClient(tmp_path, {("fix", "baseline"): "incorrect"})
    original = compare.execute(output, authorization, client=client)
    assert original["counts"]["fix"] == original["counts"]["unchanged_correct"] == 1
    for case, role in (("fix", "candidate"), ("same", "baseline")):
        directory = output / "results" / f"{case}-{role}-1"
        answer = directory / "answer.json"
        content = answer.read_bytes()
        record = (directory / "result.json").read_bytes()
        for mutation, error in ((None, "missing_retained_output"),
                                (content + b" ", "retained_output_hash_mismatch")):
            if mutation is None:
                answer.unlink()
            else:
                answer.write_bytes(mutation)
            result = compare.report(output)
            pair = next(p for p in result["pairs"] if p["case_id"] == case)
            assert pair["outcome"] == "inconclusive"
            assert pair[role]["verdict"] == "INCONCLUSIVE"
            assert pair[role]["evaluation_error"] == error
            assert result["conditions"][role]["evaluation_errors"] == 1
            assert result["counts"]["fix" if case == "fix" else "unchanged_correct"] == 0
            assert result["counts"]["regression"] == 0
            assert (directory / "result.json").read_bytes() == record
            answer.write_bytes(content)
            assert compare.report(output) == original
    assert len(client.calls) == 4


def test_git_replacement_refs_do_not_substitute_snapshot_or_diff(tmp_path):
    config, repo = configuration(tmp_path, ids=("one",))
    raw = json.loads(config.read_text())
    before, after = (raw["snapshots"][role]["git_revision"] for role in compare.ROLES)
    resource = ":library/selected/resource.txt"
    old_blob = git(repo, "rev-parse", before + resource)
    new_blob = git(repo, "rev-parse", after + resource)
    git(repo, "replace", before, after)
    git(repo, "replace", old_blob, new_blob)
    assert "New body" in git(repo, "show", before + ":library/selected/SKILL.md")
    output = tmp_path / "run"
    compare.prepare(config, repo, output)
    plan = compare.load_plan(output)
    baseline = output / "plan/bundles/baseline/selected"
    assert "Old body" in (baseline / "SKILL.md").read_text(encoding="utf-8")
    assert (baseline / "resource.txt").read_bytes() == b"old resource"
    assert any("selected/SKILL.md" in change for change in plan["source_changes"])
    assert plan["arms"]["baseline"]["git_revision"] == before


def test_changed_runtime_controllers_reject_execution_and_report_without_calls(tmp_path):
    # Load a real controller copy so filesystem changes cannot affect concurrent tests.
    runtime = tmp_path / "runtime"
    for name in (*compare.CONTROLLERS, "tools/skill_eval_verifier.py"):
        target = runtime / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    spec = importlib.util.spec_from_file_location(
        "comparison_runtime", runtime / "tools/skill_eval_compare.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config, repo = configuration(tmp_path, ids=("one",))
    output = tmp_path / "run"
    authorization = module.prepare(config, repo, output)
    module.report(output)
    saved = (output / "report.json").read_bytes(), (output / "report.md").read_bytes()
    assert "src/inferrsi/infra/executors/local.py" in module.CONTROLLERS
    assert "src/inferrsi/infra/processes.py" in module.CONTROLLERS
    client = FixedOutputClient(tmp_path)
    for name in module.CONTROLLERS:
        target = runtime / name
        original = target.read_bytes()
        target.write_bytes(original + b"\n# Changed after the plan was frozen.\n")
        with pytest.raises(ValueError, match="Controller changed after freeze"):
            module.execute(output, authorization, client=client)
        with pytest.raises(ValueError, match="Controller changed after freeze"):
            module.report(output)
        assert not (output / "results/start.json").exists()
        assert saved == ((output / "report.json").read_bytes(), (output / "report.md").read_bytes())
        target.write_bytes(original)
    assert client.calls == []


@pytest.mark.parametrize("extra", [
    {"answer": "hidden"}, {"expected": "hidden"}, {"expected_answer": "hidden"},
    {"oracle": {"answer": "hidden"}}, {"metadata": {"answer": "hidden"}},
    {"contract": {"min_reduction_pct": 20, "oracle": "hidden"}},
    {"evidence_keys": [{"answer": "hidden"}]},
    {"candidate": {"workload": {"steps": 8, "metadata": {"answer": "hidden"}}}},
])
def test_answer_keys_are_rejected_by_supported_input_shape(tmp_path, extra):
    config, repo = configuration(tmp_path, ids=("one",))
    cases = tmp_path / "cases.json"
    tasks = json.loads(cases.read_text())
    tasks[0].update(extra)
    write_json(cases, tasks)
    output = tmp_path / "run"
    with pytest.raises(ValueError, match="input"):
        compare.prepare(config, repo, output)
    assert not output.exists()
