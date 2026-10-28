import copy
import io
import stat
import sys
import threading
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
import yaml

from inferrsi.infra.artifacts import sha256, write_json
from tests.fixtures.skill_eval_compare_support import ROOT, FixedOutputClient, git
from tests.fixtures.skill_eval_pr_support import (
    SimulatedGitHub,
    SimulatedWorkflowHistory,
    approval,
    envelope,
    setup,
)
from tools import skill_eval_compare as compare
from tools import skill_eval_pr as integration


@pytest.mark.parametrize("mode", ["addition", "update"])
def test_plan_selects_addition_update_resources_without_execution(tmp_path, mode):
    repo, mapping, identity = setup(tmp_path, mode)
    output = tmp_path / "planned"
    plan = integration.prepare(repo, mapping, identity, output)
    item = plan["comparisons"][0]
    assert item["mode"] == mode and item["calls"] == 12
    assert item["exam"]["grader"] == sha256(ROOT / "tools/skill_eval_verifier.py")
    frozen = compare.load_plan(output / "selected")
    assert (frozen["arms"]["baseline"]["bundle"] is None) == (mode == "addition")
    assert frozen["arms"]["candidate"]["git_revision"] == identity["head"]
    assert all(c["coverage"] == "covered" for c in plan["coverage"]
               if c["path"].startswith("library/selected/"))
    if mode == "update":
        assert {c["coverage"] for c in plan["coverage"] if c["path"] == "exam.txt"} == {"uncovered"}
    assert list((output / "selected/results").iterdir()) == []
    second = integration.prepare(repo, mapping, identity, tmp_path / "same-plan")
    assert integration.fingerprint(plan) == integration.fingerprint(second)
    assert integration.execution_id(plan) == integration.execution_id(second)


@pytest.mark.parametrize("skill,mode", [
    ("audit-fixed-workload-claim", "addition"),
    ("inference-benchmark-design", "update"),
])
def test_maintained_mapping_selects_real_acceptance_paths(tmp_path, skill, mode):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "--quiet")
    (repo / "seed.txt").write_text("Before acceptance change", encoding="utf-8")
    mapping = compare.read_json(integration.MAPPING)
    owner = next(item for item in mapping["skills"] if item["skill"] == skill)
    path = repo / mapping["skill_root"] / owner["entrypoint"]
    index = repo / mapping["skill_root"] / "skill-index.json"
    registration = {"schema_version": 1, "skills": {
        skill: {"path": path.parent.relative_to(index.parent).as_posix(), "backend": "common"}}}
    body = f"---\nname: {skill}\ndescription: Fixed-workload audit fixture\n---\n"
    if mode == "update":
        path.parent.mkdir(parents=True)
        path.write_text(body + "Old audit guidance\n", encoding="utf-8")
        write_json(index, registration)
        git(repo, "add", mapping["skill_root"])
    git(repo, "add", "seed.txt")
    git(repo, "commit", "--quiet", "-m", "Fixture acceptance baseline")
    before = git(repo, "rev-parse", "HEAD")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body + "Audit every request and retain late outliers\n", encoding="utf-8")
    write_json(index, registration)
    git(repo, "add", mapping["skill_root"])
    git(repo, "commit", "--quiet", "-m", "Fixture acceptance candidate")
    head = git(repo, "rev-parse", "HEAD")
    plan = integration.prepare(repo, integration.MAPPING,
        {"repository": "example/fixture", "pr": 7, "base": before,
         "head": head, "version": head}, tmp_path / "planned")
    assert len(plan["comparisons"]) == 1 and plan["estimated_calls"] == 2
    selected = plan["comparisons"][0]
    assert selected["skill"] == skill and selected["mode"] == mode
    assert selected["cases"] == [{"id": "audit-threshold", "split": "holdout"}]
    assert selected["exam"]["grader"] == sha256(ROOT / "tools/skill_eval_verifier.py")
    assert {"status": "A" if mode == "addition" else "M",
        "path": path.relative_to(repo).as_posix(), "coverage": "covered"} in plan["coverage"]
    assert [change for change in plan["coverage"] if change["coverage"] != "covered"] == (
        [{"status": "A", "path": index.relative_to(repo).as_posix(), "coverage": "uncovered"}]
        if mode == "addition" else [])
    assert plan["model"] == {"name": "gpt-6.1-sol", "effort": "xhigh"}
    assert integration.budget(plan)["comparisons"] == 1
    assert not (tmp_path / "planned/execution-claim.json").exists()


def test_deleted_and_unmapped_skill_changes_are_visible_not_passed(tmp_path):
    repo, mapping, identity = setup(tmp_path)
    git(repo, "rm", "library/selected/resource.txt")
    (repo / "library/unknown").mkdir()
    (repo / "library/unknown/SKILL.md").write_text("Unmapped skill", encoding="utf-8")
    git(repo, "add", "library")
    git(repo, "commit", "--quiet", "-m", "Fixture unsupported deletion and unknown skill")
    identity.update(base=identity["head"], head=git(repo, "rev-parse", "HEAD"))
    plan = integration.prepare(repo, mapping, identity, tmp_path / "plan")
    assert plan["comparisons"] == [] and plan["estimated_calls"] == 0
    assert {c["coverage"] for c in plan["coverage"]} == {"uncovered", "unsupported"}
    body = integration.summary(plan, [], "https://github.com/example/fixture/actions/runs/1", 10, 1)
    assert "uncovered" in body and "unsupported" in body and '"fix":0' in body
    with pytest.raises(ValueError, match="No supported comparisons"):
        approval(plan)


@pytest.mark.parametrize("skill", ["../../escape", "selected/child", "Selected", "", "."])
def test_mapping_skill_ids_are_validated_before_building_output_paths(tmp_path, skill):
    repo, mapping, identity = setup(tmp_path)
    raw = compare.read_json(mapping)
    raw["skills"][0]["skill"] = skill
    write_json(mapping, raw)
    output = tmp_path / "plan"
    with pytest.raises(ValueError):
        integration.prepare(repo, mapping, identity, output)
    # Nothing may be written outside --output, and the config file is not created.
    assert not (tmp_path / "escape.json").exists()
    assert not (tmp_path / "escape").exists()
    assert not (output / "pr-plan.json").exists()


def test_unsupported_file_mode_does_not_disappear_or_become_a_pass(tmp_path):
    repo, mapping, identity = setup(tmp_path)
    git(repo, "update-index", "--chmod=+x", "library/selected/resource.txt")
    git(repo, "commit", "--quiet", "-m", "Fixture executable resource")
    identity["head"] = git(repo, "rev-parse", "HEAD")
    plan = integration.prepare(repo, mapping, identity, tmp_path / "plan")
    assert plan["estimated_calls"] == 0
    assert "Executable snapshot entries" in plan["comparisons"][0]["unsupported"]
    assert all(c["coverage"] == "unsupported" for c in plan["coverage"]
               if c["path"].startswith("library/selected/"))


@pytest.mark.parametrize("field", ["plan_sha256", "version", "base", "head", "budget"])
def test_authorization_requires_exact_revisions_and_budget(tmp_path, field):
    repo, mapping, identity = setup(tmp_path)
    plan = integration.prepare(repo, mapping, identity, tmp_path / "plan")
    request = {k: v for k, v in approval(plan).items() if k not in ("actor", "execution_id")}
    request[field] = "wrong"
    with pytest.raises(ValueError, match="Explicit approval"):
        integration.authorize(plan, request, "operator", "write",
                              {k: plan[k] for k in ("base", "head")})


def test_hash_knowledge_and_old_heads_do_not_grant_execution(tmp_path):
    repo, mapping, identity = setup(tmp_path)
    plan = integration.prepare(repo, mapping, identity, tmp_path / "plan")
    approved = approval(plan)
    request = {k: v for k, v in approved.items() if k not in ("actor", "execution_id")}
    for permission in ("read", "triage", "none"):
        with pytest.raises(ValueError, match="operator"):
            integration.authorize(plan, request, "reader", permission,
                                  {k: plan[k] for k in ("base", "head")})
    with pytest.raises(ValueError, match="PR changed"):
        integration.authorize(plan, request, "writer", "write",
                              {"base": plan["base"], "head": "f" * 40})
    # A changed exam/model/controller version produces another identity and approval.
    for field in ("model", "limits", "comparisons", "version", "head", "base"):
        changed = copy.deepcopy(plan)
        changed[field] = {"changed": True}
        assert integration.execution_id(changed) != approved["execution_id"]


def test_dispatch_history_blocks_duplicate_failed_cancelled_and_rerun_attempts(tmp_path):
    repo, mapping, identity = setup(tmp_path)
    plan = integration.prepare(repo, mapping, identity, tmp_path / "plan")
    title = integration.run_title(7, integration.fingerprint(plan))
    runs = [{"id": 1, "event": "workflow_dispatch", "display_title": title,
             "status": "completed", "conclusion": "cancelled"},
            {"id": 2, "event": "workflow_dispatch", "display_title": title}]
    assert integration.claim(plan, runs, 1, 1) == integration.execution_id(plan)
    for run, attempt in ((2, 1), (1, 2), (2, 2)):
        with pytest.raises(ValueError):
            integration.claim(plan, runs, run, attempt)
    with pytest.raises(ValueError):
        integration.claim(plan, [], 1, 1)


@pytest.fixture
def history_plan():
    return {"repository": "example/fixture", "pr": 7, "base": "a" * 40, "head": "b" * 40,
            "version": "c" * 40, "estimated_calls": 2,
            "limits": {"repeats": 1, "max_task_calls": 2, "timeout_seconds": 60,
                       "campaign_seconds": 900, "token_stop_new_trials": 20000},
            "comparisons": [{"plan_sha256": "d" * 64}]}


@pytest.mark.parametrize("reported_total", [1000, 1001])
def test_filtered_history_cap_cannot_authorize_an_omitted_older_execution(
    tmp_path, monkeypatch, history_plan, reported_total,
):
    title = integration.run_title(7, integration.fingerprint(history_plan))
    runs = [{"id": i, "event": "workflow_dispatch",
             "display_title": title if i in (1, 1001) else "another execution"}
            for i in range(1001, 0, -1)]
    visible = runs[:1000]
    assert runs[-1]["id"] == 1 and runs[-1]["display_title"] == title
    assert all(r["id"] != 1 for r in visible)
    responses = [{"total_count": reported_total, "workflow_runs": visible[i:i + 100]}
                 for i in range(0, 1100, 100)]
    api = SimulatedWorkflowHistory(history_plan, responses)
    inputs = {key: history_plan[key] for key in ("version", "base", "head")}
    inputs.update(pr="7", plan_sha256=integration.fingerprint(history_plan),
                  budget=integration.canonical(integration.budget(history_plan)))
    write_json(tmp_path / "event.json", {"inputs": inputs})
    write_json(tmp_path / "pr-plan.json", history_plan)
    for key, value in {"GITHUB_EVENT_PATH": str(tmp_path / "event.json"),
                       "GITHUB_REPOSITORY": "example/fixture", "GITHUB_RUN_ID": "1001",
                       "GITHUB_RUN_ATTEMPT": "1", "GITHUB_ACTOR": "fixture-operator",
                       "GITHUB_TOKEN": "offline-not-a-credential"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(integration, "GitHub", lambda repository, token: api)
    monkeypatch.setattr(sys, "argv", ["skill_eval_pr", "authorize", "--output", str(tmp_path)])
    with pytest.raises(ValueError, match="history"):
        integration.main()
    assert not (tmp_path / "approval.json").exists()
    assert api.pages_requested == [1]


@pytest.mark.parametrize("total", [0, 100, 101, 999])
def test_counted_workflow_history_accepts_complete_pages(history_plan, total):
    runs = [{"id": i + 1} for i in range(total)]
    responses = [{"total_count": total, "workflow_runs": runs[i:i + 100]}
                 for i in range(0, max(1, total), 100)]
    api = SimulatedWorkflowHistory(history_plan, responses)
    actual = api.pages("/actions/workflows/skill-eval-pr.yml/runs?event=workflow_dispatch",
                       "workflow_runs", require_complete=True)
    assert actual == runs
    assert api.pages_requested == list(range(1, len(responses) + 1))


def test_complete_workflow_history_keeps_an_older_duplicate_in_the_claim(history_plan):
    title = integration.run_title(7, integration.fingerprint(history_plan))
    runs = [{"id": i, "event": "workflow_dispatch",
             "display_title": title if i in (1, 101) else "another execution"}
            for i in range(101, 0, -1)]
    api = SimulatedWorkflowHistory(history_plan, [
        {"total_count": 101, "workflow_runs": runs[:100]},
        {"total_count": 101, "workflow_runs": runs[100:]},
    ])
    actual = api.pages("/actions/workflows/skill-eval-pr.yml/runs?event=workflow_dispatch",
                       "workflow_runs", require_complete=True)
    with pytest.raises(ValueError, match="Duplicate or uncertain"):
        integration.claim(history_plan, actual, 101, 1)
    assert integration.claim(history_plan, actual, 1, 1) == integration.execution_id(history_plan)


@pytest.mark.parametrize("responses", [
    [{"workflow_runs": []}],
    [{"total_count": None, "workflow_runs": []}],
    [{"total_count": True, "workflow_runs": [{"id": 1}]}],
    [{"total_count": -1, "workflow_runs": []}],
    [{"total_count": 2, "workflow_runs": [{"id": 1}]}],
    [{"total_count": 0, "workflow_runs": [{"id": 1}]}],
    [{"total_count": 101, "workflow_runs": [{"id": i} for i in range(100)]},
     {"total_count": 101, "workflow_runs": []}],
    [{"total_count": 101, "workflow_runs": [{"id": i} for i in range(100)]},
     {"total_count": 102, "workflow_runs": [{"id": 100}]}],
    [{"total_count": 101, "workflow_runs": [{"id": i} for i in range(100)]},
     {"total_count": 101, "workflow_runs": [{"id": 99}]}],
], ids=["missing-total", "null-total", "boolean-total", "negative-total", "short-page",
        "extra-record", "empty-last-page", "changing-total", "overlapping-pages"])
def test_workflow_history_rejects_incomplete_or_uncertain_pages(history_plan, responses):
    api = SimulatedWorkflowHistory(history_plan, responses)
    with pytest.raises(ValueError, match="history"):
        api.pages("/actions/workflows/skill-eval-pr.yml/runs?event=workflow_dispatch",
                  "workflow_runs", require_complete=True)


def test_concurrent_duplicate_calls_execute_only_one_paid_schedule(tmp_path):
    repo, mapping, identity = setup(tmp_path, ids=("one",))
    output = tmp_path / "plan"
    plan = integration.prepare(repo, mapping, identity, output)
    approved = approval(plan)
    client = FixedOutputClient(tmp_path)
    barrier = threading.Barrier(2)

    def trigger():
        barrier.wait()
        try:
            integration.execute(output, approved, client=client)
            return "executed"
        except FileExistsError:
            return "duplicate"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: trigger(), range(2)))
    assert sorted(outcomes) == ["duplicate", "executed"] and len(client.calls) == 2
    with pytest.raises(FileExistsError):
        integration.execute(output, approved, client=client)


@pytest.mark.parametrize("mode", ["addition", "update"])
def test_file_only_plan_artifact_round_trip_can_execute(tmp_path, mode):
    repo, mapping, identity = setup(tmp_path, mode, ids=("one",))
    hidden_resources = {
        ".audit-rules": "Retain every request\n",
        ".audit/threshold.txt": "Reject a fixed-workload claim above the threshold\n",
    }
    for name, content in hidden_resources.items():
        resource = repo / "library/selected" / name
        resource.parent.mkdir(parents=True, exist_ok=True)
        resource.write_text(content, encoding="utf-8")
    git(repo, "add", "library/selected")
    git(repo, "commit", "--quiet", "-m", "Fixture hidden skill resources")
    identity["head"] = git(repo, "rev-parse", "HEAD")
    prepared = tmp_path / "prepared"
    plan = integration.prepare(repo, mapping, identity, prepared)
    for name, content in hidden_resources.items():
        frozen_resource = prepared / "selected/plan/bundles/candidate/selected" / name
        assert frozen_resource.read_text(encoding="utf-8") == content
    write_json(prepared / "approval.json", approval(plan))
    workflow = yaml.safe_load((ROOT / integration.WORKFLOW).read_text(encoding="utf-8"))
    upload = next(step["with"] for step in workflow["jobs"]["plan"]["steps"]
                  if step.get("uses") == "actions/upload-artifact@v4")
    assert upload["path"] == prepared.name
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path in prepared.rglob("*"):
            relative = path.relative_to(prepared)
            # Match upload-artifact's documented dotfile and dot-directory filtering.
            hidden = any(part.startswith(".") for part in relative.parts)
            if path.is_file() and (upload.get("include-hidden-files", False) or not hidden):
                archive.write(path, relative.as_posix())
    downloaded = tmp_path / "downloaded"
    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as archive:
        assert all(not entry.is_dir() for entry in archive.infolist())
        archive.extractall(downloaded)
    assert not (downloaded / "selected/results").exists()
    assert compare.load_plan(downloaded / "selected") == compare.load_plan(prepared / "selected")
    client = FixedOutputClient(tmp_path)
    integration.execute(downloaded, compare.read_json(downloaded / "approval.json"), client=client)
    status = compare.read_json(downloaded / "selected/results/status.json")
    assert status["execution_state"] == "completed" and status["recorded_trials"] == 2
    assert len(client.calls) == 2
    with pytest.raises(FileExistsError):
        integration.execute(downloaded, approval(plan), client=client)
    assert len(client.calls) == 2


@pytest.mark.parametrize("mode", ["addition", "update"])
def test_retained_results_publish_once_retry_without_model_and_reject_stale_jobs(tmp_path, mode):
    repo, mapping, identity = setup(tmp_path, mode, token_stop_new_trials=200)
    output = tmp_path / "execution"
    plan = integration.prepare(repo, mapping, identity, output)
    client = FixedOutputClient(tmp_path, {("fix", "baseline"): "incorrect",
        ("regression", "candidate"): "incorrect", ("wrong", "baseline"): "incorrect",
        ("wrong", "candidate"): "incorrect", ("error", "candidate"): "invalid_json"})
    integration.execute(output, approval(plan), client=client)
    data = integration.result_archive(output).read_bytes()
    publisher = tmp_path / "publisher"
    integration.prepare(repo, mapping, identity, publisher)
    api = SimulatedGitHub(plan, data)
    api.fail_response = True
    with pytest.raises(ConnectionError):
        integration.publish_retained(api, publisher, 10, 11, 1)
    calls = len(client.calls)
    receipt = integration.publish_retained(api, publisher, 10, 11, 1)
    assert receipt["html_url"].endswith("issuecomment-1")
    assert len(api.comments) == 1 and len(client.calls) == calls
    body = api.comments[0]["body"]
    assert '"fix":1' in body and '"regression":1' in body
    assert '"unchanged_correct":1' in body and '"unchanged_incorrect":1' in body
    assert '"inconclusive":1' in body and '"missing_pair":1' in body
    assert identity["head"] in body and "Uncovered/unsupported" in body
    with pytest.raises(ValueError, match="Older workflow"):
        integration.publish_retained(api, publisher, 10, 9, 1)
    api.current["head"] = "f" * 40
    with pytest.raises(ValueError, match="Stale report"):
        integration.publish_retained(api, publisher, 10, 12, 1)
    assert len(api.writes) == 2 and len(client.calls) == calls


def test_new_inputs_reject_old_artifact_and_expired_evidence_loses_verifiability(tmp_path):
    repo, mapping, identity = setup(tmp_path, ids=("one",))
    output = tmp_path / "plan"
    plan = integration.prepare(repo, mapping, identity, output)
    api = SimulatedGitHub(plan)
    api.artifact["expired"] = True
    integration.publish_retained(api, output, 10, 11, 1)
    assert "EXPIRED" in api.comments[0]["body"]
    assert "Outcomes: `" not in api.comments[0]["body"]
    api.run["head_sha"] = "f" * 40
    with pytest.raises(ValueError, match="Untrusted or mismatched"):
        integration.publish_retained(api, output, 10, 12, 1)
    api.run["head_sha"] = plan["version"]
    api.change_during_read = True
    with pytest.raises(ValueError, match="PR changed before publication"):
        integration.publish_retained(api, output, 10, 12, 1)
    assert len(api.writes) == 1


@pytest.mark.parametrize("name", ["../escape", "/absolute", "selected/results/../../escape",
    "selected/results/script.py", "report.md", "pr-plan.json", "selected/validator/verify.py",
    "selected\\results\\status.json"])
def test_untrusted_archive_paths_and_scripts_are_rejected(tmp_path, name):
    repo, mapping, identity = setup(tmp_path)
    output = tmp_path / "plan"
    integration.prepare(repo, mapping, identity, output)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        member = zipfile.ZipInfo(name)
        # Preserve unsafe archive spelling even when the host normalizes ZipInfo filenames.
        member.filename = name
        archive.writestr(member, "Untrusted content must never execute")
    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as archive:
        assert archive.infolist()[0].orig_filename == name
    with pytest.raises(ValueError):
        integration.import_results(buffer.getvalue(), output)
    assert list((output / "selected/results").iterdir()) == []


def test_symlinks_and_forged_grades_are_rejected_without_executing_artifact_scripts(tmp_path):
    repo, mapping, identity = setup(tmp_path, ids=("one",))
    output = tmp_path / "plan"
    plan = integration.prepare(repo, mapping, identity, output)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        entry = zipfile.ZipInfo("selected/results/status.json")
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(entry, "/private")
    with pytest.raises(ValueError, match="regular"):
        integration.import_results(buffer.getvalue(), output)
    client = FixedOutputClient(tmp_path)
    integration.execute(output, approval(plan), client=client)
    path = output / "selected/results/one-candidate-1/result.json"
    record = compare.read_json(path)
    record["checks"] = {"passed": True, "assertions": {"fabricated": True}}
    write_json(path, record)
    write_json(path.parent / "receipt.json", {"result_sha256": sha256(path)})
    with pytest.raises(ValueError, match="trusted grader"):
        integration.reports(output)
    record["inputs_unchanged"] = "False"
    write_json(path, record)
    write_json(path.parent / "receipt.json", {"result_sha256": sha256(path)})
    with pytest.raises(ValueError, match="must be a boolean"):
        integration.reports(output)
    assert len(client.calls) == 2


def test_artifact_envelope_and_run_provenance_are_validated(tmp_path):
    repo, mapping, identity = setup(tmp_path)
    output = tmp_path / "plan"
    plan = integration.prepare(repo, mapping, identity, output)
    api = SimulatedGitHub(plan)
    for field, value in (("path", "attacker.yml"), ("event", "pull_request"),
                         ("display_title", "wrong plan"), ("status", "in_progress")):
        original = api.run[field]
        api.run[field] = value
        with pytest.raises(ValueError, match="Untrusted or mismatched"):
            integration.publish_retained(api, output, 10, 11, 1)
        api.run[field] = original
    api.data = envelope(b"not a zip")
    with pytest.raises(zipfile.BadZipFile):
        integration.publish_retained(api, output, 10, 11, 1)
    assert api.writes == []


def test_workflow_separates_execution_and_publication_credentials():
    workflow = yaml.safe_load((ROOT / integration.WORKFLOW).read_text(encoding="utf-8"))
    assert workflow["concurrency"]["cancel-in-progress"] is False
    executor = workflow["jobs"]["execute"]
    readers = {"contents": "read", "actions": "read", "pull-requests": "read"}
    assert workflow["permissions"] == {}
    assert workflow["jobs"]["plan"]["permissions"] == readers
    assert executor["permissions"] == readers
    # PR conversation writes belong only to the separate trusted publisher.
    assert workflow["jobs"]["publish"]["permissions"] == {
        **readers, "pull-requests": "write", "issues": "write"}
    for job in workflow["jobs"].values():
        checkout = next(step for step in job["steps"] if step.get("uses") == "actions/checkout@v4")
        assert checkout["with"]["persist-credentials"] is False
        assert checkout["with"]["ref"] == "${{ github.workflow_sha }}"
    step = next(s for s in executor["steps"] if "execute --output" in s.get("run", ""))
    assert "env" not in step


def test_download_redirect_drops_the_github_token():
    request = urllib.request.Request("https://api.github.com/artifact",
                                     headers={"Authorization": "Bearer offline-only"})
    redirected = integration.ArtifactRedirect().redirect_request(
        request, None, 302, "Found", {}, "https://storage.example.invalid/signed-artifact")
    assert not redirected.has_header("Authorization")


def dispatch_event(monkeypatch, root, output, inputs, mode, run_id=11):
    write_json(root / "event.json", {"inputs": inputs})
    environment = {"GITHUB_EVENT_PATH": str(root / "event.json"),
                   "GITHUB_EVENT_NAME": "workflow_dispatch",
                   "GITHUB_REPOSITORY": "example/fixture", "GITHUB_RUN_ID": str(run_id),
                   "GITHUB_RUN_ATTEMPT": "1", "GITHUB_ACTOR": "fixture-operator",
                   "GITHUB_TOKEN": "offline-not-a-credential",
                   "GITHUB_OUTPUT": str(root / "github-output")}
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(sys, "argv", ["skill_eval_pr", mode, "--output", str(output)])


@pytest.mark.parametrize("mode", ["addition", "update"])
@pytest.mark.parametrize("extra_inputs", [{}, {"source_run": "10", "budget": "not approval",
                                             "plan_sha256": "not approval"}])
def test_plan_dispatch_prepare_publish_has_no_execution_side_effects(
    tmp_path, monkeypatch, mode, extra_inputs,
):
    repo, mapping, identity = setup(tmp_path, mode, ids=("one",))
    plan = integration.prepare(repo, mapping, identity, tmp_path / "expected")
    api = SimulatedGitHub(plan)
    request = Mock(wraps=api.request)
    monkeypatch.setattr(api, "request", request)
    monkeypatch.setattr(integration, "GitHub", lambda repository, token: api)
    monkeypatch.setattr(integration, "ROOT", repo)
    monkeypatch.setattr(integration, "MAPPING", mapping)
    for name in ("authorize", "claim", "execute", "publish_retained", "result_archive"):
        monkeypatch.setattr(integration, name, Mock(side_effect=AssertionError(name)))
    monkeypatch.setattr(compare, "execute", Mock(side_effect=AssertionError("model call")))
    original_run = integration.subprocess.run
    fetches = []

    def local_git_only(command, *args, **kwargs):
        if list(command[:2]) == ["git", "fetch"]:
            fetches.append(command)
            assert command[-2:] == [identity["base"], "refs/pull/7/head"]
            return None  # The fixture already owns the required Git objects.
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr(integration.subprocess, "run", local_git_only)
    output = tmp_path / "prepared"
    inputs = {"action": "plan", "pr": "7", **extra_inputs}
    dispatch_event(monkeypatch, tmp_path, output, inputs, "prepare")
    integration.main()
    assert compare.read_json(output / "pr-plan.json") == plan and len(fetches) == 1
    dispatch_event(monkeypatch, tmp_path, output, inputs, "publish")
    api.fail_response = True
    with pytest.raises(ConnectionError):
        integration.main()
    assert len(api.writes) == 1 and len(api.comments) == 1
    dispatch_event(monkeypatch, tmp_path, output, inputs, "publish", run_id=12)
    integration.main()
    assert [write[0] for write in api.writes] == ["POST", "PATCH"]
    assert len(api.comments) == 1 and "**PLANNED:" in api.comments[0]["body"]
    assert identity["head"] in api.comments[0]["body"]
    assert not (output / "approval.json").exists()
    assert not (output / "execution-claim.json").exists()
    assert not any((output / "selected/results").iterdir())
    assert not any("/actions/" in call.args[1] or "/collaborators/" in call.args[1]
                   for call in request.call_args_list)


@pytest.mark.parametrize("mode", ["authorize", "execute", "pack"])
def test_plan_action_rejects_execution_cli_modes(tmp_path, monkeypatch, mode):
    output = tmp_path / "prepared"
    dispatch_event(monkeypatch, tmp_path, output, {"action": "plan", "pr": "7"}, mode)
    forbidden = Mock(side_effect=AssertionError("Execution path reached"))
    for name in ("GitHub", "authorize", "claim", "execute", "result_archive"):
        monkeypatch.setattr(integration, name, forbidden)
    with pytest.raises(ValueError, match="Plan-only dispatch"):
        integration.main()
    forbidden.assert_not_called()
    assert not output.exists()


def test_plan_dispatch_does_not_consume_execution_identity(history_plan):
    planned = {"id": 1, "event": "workflow_dispatch",
               "display_title": "skill-eval plan or publish PR 7"}
    execution = {"id": 2, "event": "workflow_dispatch", "display_title":
                 integration.run_title(7, integration.fingerprint(history_plan))}
    with pytest.raises(ValueError, match="Duplicate or uncertain"):
        integration.claim(history_plan, [planned], 1, 1)
    assert integration.claim(history_plan, [planned, execution], 2, 1) == (
        integration.execution_id(history_plan))


@pytest.mark.parametrize("field", ["plan_sha256", "version", "base", "head", "budget"])
@pytest.mark.parametrize("invalid", ["missing", "empty", "wrong"])
def test_execute_dispatch_requires_all_approval_inputs_before_claim(
    tmp_path, monkeypatch, history_plan, field, invalid,
):
    inputs = {key: history_plan[key] for key in ("version", "base", "head")}
    inputs.update(action="execute", pr="7", plan_sha256=integration.fingerprint(history_plan),
                  budget=integration.canonical(integration.budget(history_plan)))
    if invalid == "missing":
        del inputs[field]
    else:
        inputs[field] = "" if invalid == "empty" else "{}" if field == "budget" else "wrong"
    output = tmp_path / "prepared"
    write_json(output / "pr-plan.json", history_plan)
    api = SimulatedWorkflowHistory(history_plan, [])
    monkeypatch.setattr(integration, "GitHub", lambda repository, token: api)
    forbidden = Mock(side_effect=AssertionError("Execution identity consumed"))
    monkeypatch.setattr(integration, "claim", forbidden)
    monkeypatch.setattr(integration, "execute", forbidden)
    dispatch_event(monkeypatch, tmp_path, output, inputs, "authorize")
    with pytest.raises((KeyError, ValueError)):
        integration.main()
    forbidden.assert_not_called()
    assert api.pages_requested == []
    assert not (output / "approval.json").exists()
    assert not (output / "execution-claim.json").exists()


@pytest.mark.parametrize("source", ["automatic-plan", "manual-plan"])
def test_publish_dispatch_rejects_planning_source_before_artifact_access(
    tmp_path, monkeypatch, source,
):
    repo, mapping, identity = setup(tmp_path, ids=("one",))
    output = tmp_path / "prepared"
    plan = integration.prepare(repo, mapping, identity, output)
    api = SimulatedGitHub(plan)
    if source == "automatic-plan":
        api.run["event"] = "pull_request_target"
    else:
        api.run["display_title"] = "skill-eval plan or publish PR 7"
    request = Mock(wraps=api.request)
    monkeypatch.setattr(api, "request", request)
    monkeypatch.setattr(integration, "GitHub", lambda repository, token: api)
    dispatch_event(monkeypatch, tmp_path, output,
                   {"action": "publish", "pr": "7", "source_run": "10"}, "publish")
    with pytest.raises(ValueError, match="Untrusted or mismatched execution workflow"):
        integration.main()
    request.assert_called_once_with("GET", "/actions/runs/10")
    assert api.writes == [] and api.comments == []


@pytest.mark.parametrize("source", [None, ""])
def test_publish_dispatch_requires_source_run(tmp_path, monkeypatch, history_plan, source):
    output = tmp_path / "prepared"
    write_json(output / "pr-plan.json", history_plan)
    inputs = {"action": "publish", "pr": "7"}
    if source is not None:
        inputs["source_run"] = source
    forbidden = Mock(side_effect=AssertionError("Source validation bypassed"))
    monkeypatch.setattr(integration, "GitHub", Mock())
    monkeypatch.setattr(integration, "publish_retained", forbidden)
    dispatch_event(monkeypatch, tmp_path, output, inputs, "publish")
    with pytest.raises(ValueError, match="requires the original execution run ID"):
        integration.main()
    forbidden.assert_not_called()


def test_plan_dispatch_workflow_keeps_execution_guards():
    workflow = yaml.safe_load((ROOT / integration.WORKFLOW).read_text(encoding="utf-8"))
    # PyYAML's YAML 1.1 resolver treats the Actions key `on` as True.
    triggers = workflow.get("on", workflow.get(True))
    inputs = triggers["workflow_dispatch"]["inputs"]
    assert inputs["action"]["options"] == ["plan", "execute", "publish"]
    assert inputs["action"]["required"] and inputs["pr"]["required"]
    assert all(inputs[key]["required"] is False
               for key in ("plan_sha256", "version", "base", "head", "budget"))
    guard = "github.event_name == 'workflow_dispatch' && inputs.action == 'execute'"
    assert workflow["jobs"]["plan"]["if"] == "github.ref == 'refs/heads/main'"
    assert workflow["jobs"]["execute"]["if"] == guard
    authorize = next(step for step in workflow["jobs"]["plan"]["steps"]
                     if "authorize --output" in step.get("run", ""))
    assert authorize["if"] == guard
    assert workflow["run-name"].startswith("${{ " + guard)
