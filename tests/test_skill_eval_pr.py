import copy
import io
import stat
import threading
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest
import yaml

from inferrsi.infra.artifacts import sha256, write_json
from tests.fixtures.skill_eval_compare_support import ROOT, FixedOutputClient, git
from tests.fixtures.skill_eval_pr_support import SimulatedGitHub, approval, envelope, setup
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


def test_unsupported_file_mode_does_not_disappear_or_become_a_pass(tmp_path):
    repo, mapping, identity = setup(tmp_path)
    git(repo, "update-index", "--chmod=+x", "library/selected/resource.txt")
    git(repo, "commit", "--quiet", "-m", "Fixture executable resource")
    identity["head"] = git(repo, "rev-parse", "HEAD")
    plan = integration.prepare(repo, mapping, identity, tmp_path / "plan")
    assert plan["estimated_calls"] == 0
    assert "Executable snapshot entries" in plan["comparisons"][0]["unsupported"]


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
        archive.writestr(name, "Untrusted content must never execute")
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
    assert all(value != "write" for value in executor["permissions"].values())
    assert workflow["jobs"]["publish"]["permissions"]["issues"] == "write"
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
