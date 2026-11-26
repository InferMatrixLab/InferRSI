"""Exercise public submission from a real native export with synthetic Git/GitHub data."""

import json
import re
import shutil
from pathlib import Path

import pytest

from inferrsi.apps import delivery
from tests.apps.test_result_delivery import make_campaign, state
from tools import optimization_records as records
from tools import submit_optimization_record as submit
from tools.validate_evidence import validate_inventory

FACTS = {
    "agent_tool": "ExampleAgent",
    "agent_version": "1.2.0",
    "inferrsi_commit": "a" * 40,
    "agent_model": {"id": "example/agent", "temperature": 0.2},
    "optimized_model": {"id": "example/target", "dtype": "bfloat16", "tp": 2},
}
PRIVATE = ("private.example", "fake-secret-trace", "fake-secret-config", "fake-secret-prompt",
           "198.51.100.91")
PROMPT = "Optimize the synthetic operation.\npassword: fake-secret-prompt\nHost private.example\n"


def export_for_record(tmp_path, *, failed=False, missing_start=False, private=False):
    source = make_campaign(tmp_path, scores=(12, 5), final_verdict="FAIL" if failed else "PASS")
    if missing_start or private:
        control = source / "state.json"
        saved = state(source)
        if missing_start:
            saved.pop("started_at", None)
        if private:
            saved["rounds"][0]["hypothesis"] = "fake-secret-trace 198.51.100.91"
            saved["stop_reason"] = "private.example"
        control.write_text(json.dumps(saved), encoding="utf-8")
    if failed:
        (source / state(source)["final"]["path"] / "observation.json").unlink()
    target = tmp_path / "delivery"
    output = delivery.export_bundle(source, target)
    assert output["status"] == "published", output
    return target


def json_file(files, name):
    return json.loads(files[name])


def test_partial_record_keeps_cached_verdict_and_fallback_basis(tmp_path):
    bundle = export_for_record(tmp_path, failed=True, missing_start=True)
    folder = records.prepare_record(bundle, tmp_path, facts={}, omit_prompt=True)
    manifest, files = records.load_record(folder)
    assert re.fullmatch(records.RECORD_ID, folder.name)
    assert manifest["timestamp_basis"] == "first_capture"
    assert manifest["run_started_at"] is None
    assert manifest["omissions"]["agent_version"] == "unavailable"
    assert manifest["omissions"]["run_start"] == "unavailable"
    assert manifest["assessment_verdict"] == "FAIL"
    assert manifest["artifacts"][-1]["availability"] == "withheld"
    trace = json_file(files, "trace/02-result.json")
    assert trace["verification"] == "unverified"
    assert trace["provenance"] == "cached_state"
    assert trace["delivery_accepted"] is False
    assert trace["verdict"] == "FAIL"
    assert "prompt.md" not in files


def test_same_start_and_collision_create_distinct_records(tmp_path, monkeypatch):
    bundle = export_for_record(tmp_path)
    hexadecimal = iter(("a", "a", "b"))

    class UUID:
        hex = ""

    def next_uuid():
        item = UUID()
        item.hex = next(hexadecimal) * 32
        return item

    monkeypatch.setattr(records, "uuid4", next_uuid)
    first = records.prepare_record(bundle, tmp_path, facts=FACTS, prompt=PROMPT)
    second = records.prepare_record(bundle, tmp_path, facts=FACTS, prompt=PROMPT)
    assert first != second
    assert first.name.split("-")[0] == second.name.split("-")[0]
    manifest, files = records.load_record(second)
    assert manifest["timestamp_basis"] == "run_start"
    assert manifest["agent_version"] == "1.2.0"
    assert manifest["inferrsi_commit"] == "a" * 40
    assert json_file(files, "trace/01-execution.json")["attempts"][0]["verdict"] == "FAIL"
    assert json_file(files, "trace/02-result.json")["verdict"] == "PASS"
    assert json_file(files, "trace/02-result.json")["metrics"] is None


def test_invalid_export_does_not_publish_a_partial_record(tmp_path):
    bundle = export_for_record(tmp_path)
    (bundle / "campaign-result.json").write_text("{}", encoding="utf-8")
    before = set(tmp_path.iterdir())
    with pytest.raises(ValueError, match="integrity"):
        records.prepare_record(bundle, tmp_path, facts={})
    assert set(tmp_path.iterdir()) == before


def test_measured_values_keep_source_units_with_public_acceptance_reference(tmp_path):
    bundle = export_for_record(tmp_path)
    folder = records.prepare_record(bundle, tmp_path, facts=FACTS, acceptance_issue=1)
    manifest, files = records.load_record(folder)
    assert manifest["acceptance_issue"] == 1
    final = next(row for row in json_file(files, "trace/02-result.json")["metrics"]
                 if row["phase"] == "final")
    assert (final["name"], final["unit"], final["statistic"]) == ("latency", "ms", "median")
    assert final["sample_counts"] == {"baseline": 2, "candidate": 2}


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    root = tmp_path / "checkout"
    root.mkdir()
    monkeypatch.chdir(root)
    submit.git("init", "-b", "main")
    submit.git("config", "user.name", "Example Contributor")
    submit.git("config", "user.email", "contributor@example.invalid")
    submit.git("config", "core.autocrlf", "false")
    submit.git("config", "commit.gpgsign", "false")
    records_dir = root / "evidence/records"
    records_dir.mkdir(parents=True)
    (records_dir / "README.md").write_text("Synthetic layout\n", encoding="utf-8")
    submit.git("add", ".")
    submit.git("commit", "-m", "Synthetic base")
    submit.git("update-ref", submit.BASE_REF, "HEAD")
    submit.git("remote", "add", "origin", "https://github.com/example-user/InferRSI.git")
    return root


def test_ordinary_submission_reviews_exact_bytes_and_reuses_pr(tmp_path, checkout, monkeypatch):
    bundle = export_for_record(tmp_path, private=True)
    facts = {**FACTS, "optimized_model": {
        "id": "private.example", "backend": "198.51.100.91", "token": "fake-secret-config",
        "dtype": "bfloat16",
    }}
    prepared = records.prepare_record(bundle, tmp_path, facts=facts, prompt=PROMPT)
    submit.git("switch", "-c", submit.branch_name(prepared.name))
    assert submit.stage(prepared) == Path("evidence/records") / prepared.name
    attribution = "ExampleAgent / example-model [effort=high] (author)"
    staged = submit.review(prepared.name, attribution)
    assert staged["repository"] == "InferMatrixLab/InferRSI"
    assert staged["base"] == "main"
    assert staged["commit"]["author"] == staged["commit"]["committer"]
    assert f"Agent-assisted-by: {attribution}" in staged["commit"]["message"]
    assert len(staged["files"]) == 5
    _, staged_files = records.load_record(checkout / submit.RECORD_ROOT / prepared.name)
    public = repr(staged).encode() + b"".join(staged_files.values())
    assert all(secret.encode() not in public for secret in PRIVATE)
    assert b"Optimize the synthetic operation" in staged_files["prompt.md"]
    assert b"redacted-credential-line" in staged_files["prompt.md"]
    assert json_file(staged_files, "model-config.json")["optimized_model"]["id"] is None

    command = submit.command
    operations = []
    prs = []

    def stub(*args):
        if args[:2] == ("git", "push"):
            operations.append("push")
            assert args[-1] == (
                submit.git("rev-parse", "HEAD").decode().strip()
                + ":refs/heads/" + staged["branch"]
            )
            return b""
        if args[:3] == ("gh", "repo", "view"):
            return records.json_bytes({
                "nameWithOwner": staged["push_repository"],
                "parent": {"nameWithOwner": records.REPOSITORY},
            })
        if args[:2] == ("gh", "api"):
            assert f"repos/{records.REPOSITORY}/pulls" in args
            assert f"head=example-user:{staged['branch']}" in args
            return records.json_bytes(prs)
        if args[:3] == ("gh", "pr", "create"):
            operations.append("create")
            assert args[args.index("--base") + 1] == "main"
            assert args[args.index("--repo") + 1] == records.REPOSITORY
            assert args[args.index("--title") + 1] == staged["title"]
            body = Path(args[args.index("--body-file") + 1]).read_text(encoding="utf-8")
            assert body == staged["body"]
            prs.append({
                "base": {"ref": "main", "repo": {"full_name": records.REPOSITORY}},
                "head": {"ref": staged["branch"],
                         "repo": {"full_name": staged["push_repository"]},
                         "sha": submit.git("rev-parse", "HEAD").decode().strip()},
                "html_url": f"https://github.com/{records.REPOSITORY}/pull/1",
                "title": staged["title"], "body": body, "state": "open", "merged_at": None,
            })
            return b""
        return command(*args)

    monkeypatch.setattr(submit, "command", stub)
    with pytest.raises(ValueError, match="exact reviewed"):
        submit.publish(prepared.name, "unapproved", attribution)
    assert not operations
    assert submit.review(prepared.name, attribution)["committed_head"] is None
    (checkout / "unexpected.txt").write_text("Unrelated", encoding="utf-8")
    submit.git("add", "unexpected.txt")
    with pytest.raises(ValueError, match="PR diff"):
        submit.publish(prepared.name, staged["review_digest"], attribution)
    submit.git("restore", "--staged", "unexpected.txt")
    (checkout / "unexpected.txt").unlink()
    expected = f"https://github.com/{records.REPOSITORY}/pull/1"
    assert submit.publish(prepared.name, staged["review_digest"], attribution) == expected
    assert submit.publish(prepared.name, staged["review_digest"], attribution) == expected
    prs[0]["title"] = "Different title"
    with pytest.raises(ValueError, match="approved title/body"):
        submit.publish(prepared.name, staged["review_digest"], attribution)
    prs[0]["title"] = staged["title"]
    prs[0]["body"] = "Different body"
    with pytest.raises(ValueError, match="approved title/body"):
        submit.publish(prepared.name, staged["review_digest"], attribution)
    prs[0]["body"] = staged["body"]
    prs[0]["state"] = "closed"
    with pytest.raises(ValueError, match="closed without merging"):
        submit.publish(prepared.name, staged["review_digest"], attribution)
    prs[0]["merged_at"] = "2026-01-01T00:00:00Z"
    assert submit.publish(prepared.name, staged["review_digest"], attribution) == expected
    assert operations == ["push", "create"]
    assert b"Signed-off-by: Example Contributor <contributor@example.invalid>" in submit.git(
        "log", "-1", "--format=%B"
    )


@pytest.mark.parametrize("changed", ["message", "identity", "signoff"])
def test_retry_refuses_unapproved_commit_metadata(tmp_path, checkout, monkeypatch, changed):
    bundle = export_for_record(tmp_path)
    prepared = records.prepare_record(bundle, tmp_path, facts=FACTS)
    submit.git("switch", "-c", submit.branch_name(prepared.name))
    submit.stage(prepared)
    review = submit.review(prepared.name, None)
    expected = review["commit"]["message"]
    message = tmp_path / "message.txt"
    if changed == "message":
        message.write_text("Unexpected public text\n\n" + expected, encoding="utf-8")
    elif changed == "signoff":
        message.write_text(expected.split("\n\n")[0] + "\n", encoding="utf-8")
    else:
        message.write_text(expected, encoding="utf-8")
    author = ("--author", "Different Contributor <different@example.invalid>") if (
        changed == "identity"
    ) else ()
    submit.git("commit", "--cleanup=verbatim", "-F", str(message), *author)
    command = submit.command

    def checked(*args):
        assert args[0] == "git" and args[1] != "push", "Publication must stop before network I/O"
        return command(*args)

    monkeypatch.setattr(submit, "command", checked)
    with pytest.raises(submit.SubmissionError, match="Commit metadata differs"):
        submit.publish(prepared.name, review["review_digest"], None)


@pytest.mark.parametrize("damage", [None, "traversal", "tampered", "stray", "symlink"])
def test_record_inventory_and_campaign_checks_coexist(tmp_path, damage):
    repo = tmp_path / "repo"
    records_root = repo / "evidence/records"
    records_root.mkdir(parents=True)
    (records_root / "README.md").write_text("Synthetic documentation", encoding="utf-8")
    campaign = repo / "evidence/synthetic-campaign"
    for name in ("plan", "results", "patch", "validator"):
        (campaign / name).mkdir(parents=True)
    inventory = repo / "tools/evidence_inventory.json"
    inventory.parent.mkdir()
    inventory.write_bytes(records.json_bytes({"version": 1, "bundles": {
        "records": {"kind": "optimization-records", "manifests": []},
        "synthetic-campaign": {"kind": "campaign", "manifests": []},
    }}))
    bundle = export_for_record(tmp_path)
    folder = records.prepare_record(bundle, records_root, facts=FACTS)
    if damage == "traversal":
        manifest = folder / "record.json"
        data = records.read_object(manifest)
        data["artifacts"][0]["path"] = "../README.md"
        manifest.write_bytes(records.json_bytes(data))
    elif damage == "tampered":
        (folder / "model-config.json").write_text("{}", encoding="utf-8")
    elif damage == "stray":
        shutil.copyfile(folder / "record.json", folder / "unsanitized.json")
    elif damage == "symlink":
        payload = folder / "model-config.json"
        alias = folder / "symlink-target.json"
        payload.rename(alias)
        try:
            payload.symlink_to(alias)
        except OSError:
            pytest.skip("symlinks unavailable")
    result = validate_inventory(repo)
    if damage:
        assert "invalid record" in str(result["errors"])
    else:
        assert result["errors"] == []
        assert result["checked_hashes"] == 3
