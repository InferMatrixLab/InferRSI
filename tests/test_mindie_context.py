"""Offline MindIE fixtures; these tests do not establish a real knowledge/NPU run."""

import hashlib
import json
import shutil
import subprocess
import sys

import pytest

from inferrsi.cli import main
from inferrsi.harness.campaign_records import create_campaign
from inferrsi.harness.dashboard_data import load_dashboard
from inferrsi.mindie_context import export_context

REF = "mindie://vllm-ascend/units/unit-precision@2"
PREMISE = "mindie://vllm-ascend/units/unit-fp32@1"


@pytest.fixture
def evidence(tmp_path):
    campaign = tmp_path / "campaign"
    create_campaign(campaign, "example")
    documents = {
        "query_input": {"query": "Precision guidance for a vector reduction", "conditions": {
            "dtype": "float32", "input_shape": [[2, 17], [3, 9]]}},
        "query_result": {"isError": False, "structuredContent": {"results": [
            {"ref": REF}, *({"ref": f"mindie://vllm-ascend/units/unit-other-{i}@1"}
                           for i in range(4))]}},
        "explain_input": {"refs": [REF], "conditions": {"dtype": "float32"},
                          "known_refs": [], "token_budget": 16000},
        "explain_result": {"isError": False, "structuredContent": {
            "units": [{"id": "unit-precision", "revision": 2,
                       "content": "Fixture: preserve reduction precision.\nSecond line.\n"}],
            "requires": [{"id": "unit-fp32", "revision": 1,
                          "content": "Fixture prerequisite: inspect dtype.\n"}],
            "unresolved": []}},
    }
    paths = {}
    for key, value in documents.items():
        paths[key] = tmp_path / (key + ".json")
        paths[key].write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return campaign, paths, documents


def export(evidence, **overrides):
    campaign, paths, _ = evidence
    return export_context(campaign, context_id="read-r1", **paths,
                          query_exit_code=overrides.get("query_exit_code", 0),
                          explain_exit_code=overrides.get("explain_exit_code", 0))


def rewrite(evidence, key):
    _, paths, documents = evidence
    paths[key].write_text(json.dumps(documents[key]), encoding="utf-8")


def trace_template(context, *, run_id="run-a", candidate="candidate-v1", round_number=1):
    return {"schema_version": 1, "reviewed_by_caller": True,
            "campaign_id": "example", "candidate_id": candidate, "round": round_number,
            "run_id": run_id, "context": context,
            "search_space": {"state": "complete", "items": [], "missing_reason": ""},
            "steps": {"state": "complete", "items": [], "missing_reason": ""},
            "summary": {"state": "partial", "successes": [], "failures": [],
                        "limitations": ["CPU fixture only"], "missing_reason": "No NPU run"}}


def test_cli_retains_only_delivered_bodies_and_exact_raw_bytes(evidence, capsys):
    campaign, paths, _ = evidence
    args = ["campaign", "import-mindie", "--directory", str(campaign), "--id", "read-r1",
            "--query-exit-code", "0", "--explain-exit-code", "0"]
    for key, path in paths.items():
        args += ["--" + key.replace("_", "-"), str(path)]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["reviewed_by_caller"] is False
    target = campaign / "mindie/read-r1"
    context = json.loads((target / "context.json").read_text())
    assert context["text"] == "" and context["state"] == "complete"
    assert [source["ref"] for source in context["sources"]] == [PREMISE, REF]
    assert [source["revision"] for source in context["sources"]] == ["1", "2"]
    assert context["sources"][1]["locator"].endswith("#/structuredContent/units/0/content")
    body = (target / "reviewed-context.txt").read_text()
    assert body.index(PREMISE) < body.index(REF)
    assert "Fixture: preserve reduction precision.\nSecond line.\n" in body
    assert "unit-other" not in body
    receipt = json.loads((target / "receipt.json").read_text())
    for key, path in paths.items():
        name = key.replace("_", "-") + ".json"
        assert (target / name).read_bytes() == path.read_bytes()
        assert receipt["sha256"][name] == hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(SystemExit):
        main(args)


@pytest.mark.parametrize("form", ["direct", "text"])
def test_documented_payload_forms(evidence, form):
    _, _, docs = evidence
    for key in ("query_result", "explain_result"):
        payload = docs[key]["structuredContent"]
        docs[key] = payload if form == "direct" else {
            "isError": False, "content": [{"type": "text", "text": json.dumps(payload)}]}
        rewrite(evidence, key)
    assert (export(evidence) / "reviewed-context.txt").is_file()


@pytest.mark.parametrize("failure", ["inactive", "query_error", "read_error", "exit", "missing",
                                     "no_body", "wrong_revision", "wrong_request"])
def test_failed_or_unavailable_reads_do_not_become_context(evidence, failure):
    campaign, paths, docs = evidence
    if failure in {"inactive", "query_error", "read_error"}:
        key = "query_result" if failure == "query_error" else "explain_result"
        docs[key] = {"isError": True, "content": [{"type": "text", "text": "FIXTURE_PRIVATE"}]}
        rewrite(evidence, key)
    elif failure == "missing":
        paths["explain_result"].unlink()
    elif failure == "no_body":
        payload = docs["explain_result"]["structuredContent"]
        payload.update(units=[], requires=[], unresolved=[{"ref": REF, "status": "not_found"}])
        rewrite(evidence, "explain_result")
    elif failure == "wrong_revision":
        docs["explain_result"]["structuredContent"]["units"][0]["revision"] = 3
        rewrite(evidence, "explain_result")
    elif failure == "wrong_request":
        docs["explain_input"]["refs"] = [REF.replace("@2", "@3")]
        rewrite(evidence, "explain_input")
    with pytest.raises((ValueError, OSError)) as error:
        export(evidence, explain_exit_code=1 if failure == "exit" else 0)
    assert "FIXTURE_PRIVATE" not in str(error.value)
    assert not (campaign / "mindie/read-r1").exists()


def test_unresolved_is_retained_and_marks_partial(evidence):
    _, _, docs = evidence
    excluded = {"ref": "mindie://vllm-ascend/units/unit-other-0@1", "status": "budget_excluded"}
    docs["explain_input"]["refs"].append(excluded["ref"])
    docs["explain_result"]["structuredContent"]["unresolved"] = [excluded]
    rewrite(evidence, "explain_input")
    rewrite(evidence, "explain_result")
    target = export(evidence)
    context = json.loads((target / "context.json").read_text())
    assert context["state"] == "partial" and context["missing_reason"]
    assert excluded["ref"] not in [source["ref"] for source in context["sources"]]
    assert json.loads((target / "receipt.json").read_text())["unresolved"] == [excluded]


@pytest.mark.parametrize("field,value", [("candidate_id", "other"), ("round", 2),
                                         ("run_id", "other")])
def test_imported_context_obeys_existing_trace_identity_binding(evidence, field, value):
    campaign, _, _ = evidence
    target = export(evidence)
    run = campaign / "runs/run-a"
    run.mkdir(parents=True)
    (run / "run.lock.json").write_text("{}")
    document = trace_template(json.loads((target / "context.json").read_text()))
    document[field] = value
    template = campaign / "template.json"
    template.write_text(json.dumps(document))
    assert main(["campaign", "assemble-trace", "--directory", str(campaign), "--template",
                 str(template), "--context-file", str(target / "reviewed-context.txt"),
                 "--output", "optimization-v1.json"]) == 0
    with pytest.raises(SystemExit):
        main(["campaign", "record", "--directory", str(campaign), "--candidate", "candidate-v1",
              "--run-id", "run-a", "--round", "1", "--title", "v1",
              "--optimization-trace", "optimization-v1.json"])
    assert not (campaign / "candidates/candidate-v1/candidate.json").exists()


def test_v1_snapshot_is_evaluated_after_workspace_becomes_v2(evidence, tmp_path, capsys):
    campaign, _, _ = evidence
    read = export(evidence)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    implementation = "def compute(values):\n    return sum(values)\n"
    (workspace / "implementation.py").write_text(implementation)
    (workspace / "check.py").write_text(
        "from implementation import compute\nassert compute([1, 2, 3]) == 6\n")
    (workspace / "bench.py").write_text(
        "import json, pathlib, sys\nfrom implementation import compute\n"
        "observed = compute([1, 2, 3])\nassert observed == 6\n"
        "pathlib.Path(sys.argv[1]).write_text(json.dumps({"
        "'metrics': {'latency_ms': 1}, 'observed': observed}))\n")
    snapshot = tmp_path / "candidate-v1"
    shutil.copytree(workspace, snapshot)
    for args in (("init", "--quiet"), ("add", "."),
                 ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                  "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "fixture")):
        subprocess.run(["git", "-C", str(snapshot), *args], check=True, capture_output=True)
    # Generation workspace now holds v2 before any evaluation of delivered v1.
    (workspace / "implementation.py").write_text("def compute(values):\n    return 999\n")
    command = f'"{sys.executable}" -B bench.py {{result}}'
    check = f'"{sys.executable}" -B check.py'
    assert main(["run", "--repo", str(snapshot), "--candidate-repo", str(snapshot),
                 "--backend", "cpu", "--agent", "codex", "--mode", "code",
                 "--baseline-command", command, "--candidate-command", command,
                 "--validation-command", check, "--repetitions", "1", "--max-minutes", "1",
                 "--output-dir", str(campaign / "runs")]) in {0, 1}
    run_id = json.loads(capsys.readouterr().out)["run_id"]
    run = campaign / "runs" / run_id
    assert json.loads((run / "candidate/trial-001/result.json").read_text())["observed"] == 6
    document = trace_template(json.loads((read / "context.json").read_text()), run_id=run_id)
    template = campaign / "template.json"
    template.write_text(json.dumps(document))
    assert main(["campaign", "assemble-trace", "--directory", str(campaign), "--template",
                 str(template), "--context-file", str(read / "reviewed-context.txt"),
                 "--output", "optimization-v1.json"]) == 0
    assert main(["campaign", "record", "--directory", str(campaign), "--candidate", "candidate-v1",
                 "--run-id", run_id, "--round", "1", "--title", "CPU v1 fixture",
                 "--optimization-trace", "optimization-v1.json"]) == 0
    row = load_dashboard(campaign)["candidates"][0]
    assert row["run_id"] == run_id and row["optimization_trace"]["run_id"] == run_id
    assert row["optimization_trace"]["context"]["sources"][1]["ref"] == REF
    assert (snapshot / "implementation.py").read_text() == implementation
    initial = json.loads((run / "repositories.lock.json").read_text())["candidate"]
    final = json.loads((run / "repositories.final.json").read_text())["candidate"]
    assert initial["snapshot_hash"] == final["snapshot_hash"]
