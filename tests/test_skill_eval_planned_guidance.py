"""Nonpaid planner guidance: raw Git/data inspection, never candidate/model execution."""

import copy
import json
import subprocess
from unittest.mock import Mock

import pytest

from inferrsi.infra.artifacts import write_json
from tests.fixtures.skill_eval_compare_support import git
from tests.fixtures.skill_eval_pr_support import setup
from tests.test_skill_eval_pr_summary import visible
from tools import skill_eval_pr as pr


def render(plan):
    return pr.summary(plan, [], "https://example.invalid/plan", 100, 1)


def test_prepared_task_purpose_trigger_and_needed_outputs_are_retained(tmp_path, monkeypatch):
    repo, mapping, identity = setup(tmp_path, ids=("one",))
    tasks = json.loads((tmp_path / "cases.json").read_text())
    tasks[0].update(request="Audit every request against the fixed workload contract.")
    assert "arbitrary_private_note" not in pr.task_context(
        [{**tasks[0], "arbitrary_private_note": "DO-NOT-PROJECT"}])[0]
    write_json(tmp_path / "cases.json", tasks)
    never_execute = Mock(side_effect=AssertionError("No candidate or model execution"))
    monkeypatch.setattr(pr.compare, "execute", never_execute)
    plan = pr.prepare(repo, mapping, identity, tmp_path / "plan")
    item = plan["comparisons"][0]
    selection = item["selection"]
    assert selection["basis"] == "trusted_path_mapping"
    assert selection["matched_paths"] == [c["path"] for c in plan["coverage"]
                                           if c["coverage"] == "covered"]
    assert selection["tasks"][0]["request"] == tasks[0]["request"]
    assert "arbitrary_private_note" not in selection["tasks"][0]
    schema = json.loads((tmp_path / "plan/selected/plan/schema.json").read_text())
    assert selection["required_answer_fields"] == schema["required"]
    text, main = render(plan), visible(render(plan))
    for expected in (tasks[0]["request"], "http&#95;fixed&#95;workload", "Required answer fields:",
                     "python -m json.tool selected/plan/tasks.json", "**not grading**",
                     "Independent check: frozen <code>audit</code>", "git rev-parse HEAD",
                     "verified, refuted or unverified"):
        assert expected in text
    assert item["exam"]["grader"] in text and "DO-NOT-PROJECT" not in text
    assert "Outcomes:" not in text and "--execute" not in main and "--stage-local" not in main
    never_execute.assert_not_called()


def test_unsupported_and_mapping_only_keep_task_purpose_without_fake_commands(tmp_path):
    repo, mapping, identity = setup(tmp_path, ids=("one",))
    git(repo, "update-index", "--chmod=+x", "library/selected/resource.txt")
    git(repo, "commit", "--quiet", "-m", "Synthetic unsupported executable snapshot")
    identity["head"] = git(repo, "rev-parse", "HEAD")
    plan = pr.prepare(repo, mapping, identity, tmp_path / "unsupported")
    main = visible(render(plan))
    assert "Executable snapshot entries are not supported" in main
    assert plan["comparisons"][0]["selection"]["tasks"]
    assert "python -m json.tool selected" not in main
    blocked = pr.prepare(repo, mapping, identity, tmp_path / "blocked",
                         planning_blocked="unavailable configuration")
    assert blocked["comparisons"][0]["selection"]["tasks"]
    assert "Mapping-only scope; provider unavailable" in visible(render(blocked))
    assert "No supported automatic comparison" in render(plan)


def index_fixture(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "--quiet")
    canonical = repo / pr.LIBRARY_PATH / "skill-index.json"
    canonical.parent.mkdir(parents=True)
    canonical.write_text('{"fixture":"not an efficacy test"}\n')
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "Synthetic canonical source")
    pin = git(repo, "rev-parse", "HEAD")
    readme = repo / pr.PROJECTION_PATH / "README.md"
    readme.parent.mkdir(parents=True)
    readme.write_text(f"Source snapshot: [{pin}](https://github.com/example/fixture/tree/"
                      f"{pin}/{pr.LIBRARY_PATH}).\n")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "Synthetic declared projection pin")
    identity = {"repository": "example/fixture", "base": pin,
                "head": git(repo, "rev-parse", "HEAD")}
    changes = pr.changed_files(repo, identity["base"], identity["head"])
    return repo, readme, canonical, pin, identity, changes


def test_index_pin_check_uses_declared_source_not_head_and_does_not_execute(tmp_path):
    repo, _, _, pin, identity, changes = index_fixture(tmp_path)
    check = pr.projection_check(repo, identity, changes)
    assert check == {"status": "ready", "source_revision": pin,
                     "declared_in": pr.PROJECTION_PATH + "/README.md"}
    assert pin != identity["head"]
    minimal = {**identity, "version": "d" * 40, "estimated_calls": 0, "projection_check": check,
               "comparisons": [], "coverage": [{**c, "coverage": "uncovered"} for c in changes]}
    text = "\n".join(pr.author_actions(minimal))
    assert f"python tools/build_skill_index.py --source-revision {pin} --check" in text
    assert "command has **not run**" in text and "not claim truth or skill efficacy" in text
    assert "exit code and full drift/success output" in text
    assert "Generated projection paths: 1" in text


@pytest.mark.parametrize("mutation", ["missing", "malformed", "duplicate", "mismatch", "mode",
                                      "symlink", "oversized", "unknown_commit", "missing_library"])
def test_unusable_projection_pin_never_yields_a_concrete_check(tmp_path, mutation):
    repo, readme, canonical, pin, identity, changes = index_fixture(tmp_path)
    if mutation == "missing":
        readme.unlink()
    elif mutation == "malformed":
        readme.write_text("Source snapshot: $(echo unsafe)\n")
    elif mutation == "duplicate":
        readme.write_text(readme.read_text() * 2)
    elif mutation == "mismatch":
        canonical.write_text("changed canonical input\n")
    elif mutation == "mode":
        readme.chmod(0o755)
    elif mutation == "symlink":
        readme.unlink()
        readme.symlink_to(canonical)
    elif mutation == "oversized":
        readme.write_text(readme.read_text() + "x" * 65536)
    elif mutation == "unknown_commit":
        readme.write_text(readme.read_text().replace(pin, "f" * 40))
    else:
        canonical.unlink()
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "Synthetic unavailable source")
    identity["head"] = git(repo, "rev-parse", "HEAD")
    check = pr.projection_check(repo, identity, changes)
    assert check["status"] == "unavailable" and "source_revision" not in check
    if mutation == "mismatch":
        assert "differs from current canonical" in check["reason"]


def test_hostile_metadata_is_escaped_and_raw_plan_is_not_mutated(tmp_path):
    repo, mapping, identity = setup(tmp_path, ids=("one",))
    plan = pr.prepare(repo, mapping, identity, tmp_path / "plan")
    hostile = '</details><script>@all</script>\n```bash\n$(touch bad)'
    item = plan["comparisons"][0]
    item["selection"]["tasks"][0].update(request=hostile, provenance=hostile)
    item["selection"]["matched_paths"] = [hostile]
    item["selection"]["required_answer_fields"] = [hostile]
    plan["coverage"].append({"path": hostile, "coverage": "uncovered"})
    original = copy.deepcopy(plan)
    text = render(plan)
    assert text.count("</details>") == 3
    assert "<script>" not in text and "@all" not in text and "\n$(touch bad)" not in text
    assert plan == original
    plan["comparisons"] = [{"skill": "selected", "unsupported": hostile}]
    assert "<script>" not in render(plan) and "@all" not in render(plan)


def test_grouping_is_location_only_and_preserves_every_gap(tmp_path):
    repo, mapping, identity = setup(tmp_path, ids=("one",))
    plan = pr.prepare(repo, mapping, identity, tmp_path / "plan")
    plan.update(comparisons=[], estimated_calls=0)
    paths = [f"{pr.LIBRARY_PATH}/owner-{i}.md" for i in range(7)] + [
        f"{pr.PROJECTION_PATH}/record-{i}.json" for i in range(58)]
    plan["coverage"] = [{"path": p, "coverage": "uncovered"} for p in paths]
    text = render(plan)
    main = visible(text)
    assert "Canonical library paths: 7; Generated projection paths: 58; Other paths: 0" in main
    assert "These are paths, not independent claims" in main
    assert "no metadata-only conclusion is inferred" in text
    assert "Outcomes:" not in text
    assert all(path in text for path in paths)
    assert len(main) < 4300
    # This retained plan still has no automatic comparison; no new mapping was invented.
    assert not plan["comparisons"] and "python -m json.tool" not in main


@pytest.mark.parametrize("reason,category", [
    ("Invalid skill YAML: /private/owner: SECRET-CANARY", "Invalid skill YAML"),
    ("Missing declared skill document: /private/SECRET-CANARY", "Missing declared skill document"),
    ("Unsafe bundle path: SECRET-CANARY", "Unsafe bundle path"),
    ("arbitrary SECRET-CANARY exception", "unrecognized reason"),
    ({"private": "SECRET-CANARY"}, "unrecognized reason"),
])
def test_public_failure_categories_do_not_echo_raw_suffix_or_unknown_text(
        tmp_path, reason, category):
    repo, mapping, identity = setup(tmp_path, ids=("one",))
    plan = pr.prepare(repo, mapping, identity, tmp_path / "plan")
    plan.update(comparisons=[{"skill": "selected", "unsupported": reason}], estimated_calls=0)
    original = copy.deepcopy(plan)
    text = render(plan)
    assert category in visible(text) and category in text
    assert "SECRET-CANARY" not in text and "/private/" not in text
    assert plan == original


def test_reachable_malformed_skill_yaml_retains_raw_reason_but_projects_only_category(tmp_path):
    repo, mapping, identity = setup(tmp_path, ids=("one",))
    skill = repo / "library/selected/SKILL.md"
    skill.write_text("---\nname: selected\ndescription: [SECRET-CANARY\n---\n")
    git(repo, "add", "library/selected/SKILL.md")
    git(repo, "commit", "--quiet", "-m", "Synthetic malformed YAML public-display control")
    identity["head"] = git(repo, "rev-parse", "HEAD")
    output = tmp_path / "plan"
    plan = pr.prepare(repo, mapping, identity, output)
    original = (output / "pr-plan.json").read_bytes()
    reason = plan["comparisons"][0]["unsupported"]
    assert reason.startswith("Invalid skill YAML:") and "SECRET-CANARY" in reason
    text = render(plan)
    assert "Invalid skill YAML" in visible(text) and "SECRET-CANARY" not in text
    assert (output / "pr-plan.json").read_bytes() == original



def test_plan_and_publisher_full_history_keep_projection_fingerprint_identical(tmp_path):
    # Actual local Git transport, not a stubbed metadata/availability response.
    # No candidate checkout/import, model invocation, external network or credentials.
    repo, readme, _, pin, _, _ = index_fixture(tmp_path)
    base = git(repo, "rev-parse", "HEAD")
    readme.write_text(readme.read_text() + "\nSynthetic PR projection change.\n")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "Synthetic PR head after shallow base")
    head = git(repo, "rev-parse", "HEAD")
    remote = tmp_path / "remote.git"
    git(tmp_path, "clone", "--quiet", "--bare", str(repo), str(remote))
    git(remote, "update-ref", "refs/heads/main", base)
    git(remote, "update-ref", "refs/pull/7/head", head)
    git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
    shallow, publisher = tmp_path / "shallow", tmp_path / "publisher"
    for destination, depth in ((shallow, ["--depth", "1"]), (publisher, [])):
        git(tmp_path, "clone", "--quiet", "--no-checkout", "--branch", "main", *depth,
            remote.as_uri(), str(destination))
        # Same explicit base + PR ref fetch as the existing workflow entrypoint.
        git(destination, "fetch", "--no-tags", "--no-recurse-submodules", remote.as_uri(),
            base, "refs/pull/7/head")
    assert git(shallow, "rev-parse", "--is-shallow-repository") == "true"
    assert git(publisher, "rev-parse", "--is-shallow-repository") == "false"
    mapping = tmp_path / "mapping.json"
    write_json(mapping, {"skills": [], "skill_root": pr.LIBRARY_PATH,
                        "model": {"name": "offline-fixture", "effort": "test"},
                        "limits": {"repeats": 1, "max_task_calls": 2, "timeout_seconds": 60,
                                   "campaign_seconds": 600, "token_stop_new_trials": 1000}})
    identity = {"repository": "example/fixture", "pr": 7, "base": base,
                "head": head, "version": base}
    old = pr.prepare(shallow, mapping, identity, tmp_path / "old-shallow-plan")
    published = pr.prepare(publisher, mapping, identity, tmp_path / "full-publisher-plan")
    assert old["projection_check"]["status"] == "unavailable"
    assert published["projection_check"] == {"status": "ready", "source_revision": pin,
                                            "declared_in": pr.PROJECTION_PATH + "/README.md"}
    assert pr.fingerprint(old) != pr.fingerprint(published)  # Reproduces the native finding.
    git(shallow, "fetch", "--unshallow", "--no-tags", "--no-recurse-submodules", remote.as_uri())
    repaired = pr.prepare(shallow, mapping, identity, tmp_path / "full-plan")
    assert repaired == published and pr.fingerprint(repaired) == pr.fingerprint(published)
    assert not repaired["comparisons"] and repaired["estimated_calls"] == 0



def test_unrelated_source_ref_presence_cannot_change_full_history_plan(tmp_path):
    repo, readme, _, _, _, _ = index_fixture(tmp_path)
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    unrelated = git(repo, "commit-tree", tree, "-m", "Synthetic unrelated source with same library")
    readme.write_text(f"Source snapshot: [{unrelated}](https://github.com/example/fixture/tree/"
                      f"{unrelated}/{pr.LIBRARY_PATH}).\n")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "Synthetic nonancestor declaration")
    head = git(repo, "rev-parse", "HEAD")
    remote = tmp_path / "remote.git"
    git(tmp_path, "clone", "--quiet", "--bare", str(repo), str(remote))
    # The orphan object is not copied merely by naming its SHA in README.
    git(repo, "update-ref", "refs/heads/source-only", unrelated)
    git(remote, "fetch", str(repo), "refs/heads/source-only:refs/heads/source-only")
    git(remote, "update-ref", "refs/heads/main", head)
    git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
    cached, absent = tmp_path / "cached", tmp_path / "absent"
    git(tmp_path, "clone", "--quiet", "--no-checkout", remote.as_uri(), str(cached))
    git(remote, "update-ref", "-d", "refs/heads/source-only")
    git(tmp_path, "clone", "--quiet", "--no-checkout", remote.as_uri(), str(absent))
    assert git(cached, "cat-file", "-t", unrelated) == "commit"
    missing = subprocess.run(["git", "cat-file", "-e", unrelated], cwd=absent,
                             capture_output=True, check=False)
    assert missing.returncode != 0
    mapping = tmp_path / "mapping.json"
    write_json(mapping, {"skills": [], "skill_root": pr.LIBRARY_PATH,
                        "model": {"name": "offline-fixture", "effort": "test"},
                        "limits": {"repeats": 1, "max_task_calls": 2, "timeout_seconds": 60,
                                   "campaign_seconds": 600, "token_stop_new_trials": 1000}})
    identity = {"repository": "example/fixture", "pr": 7, "base": git(repo, "rev-parse", "HEAD^"),
                "head": head, "version": head}
    plans = []
    for index, clone in enumerate((cached, absent)):
        assert git(clone, "rev-parse", "--is-shallow-repository") == "false"
        plans.append(pr.prepare(clone, mapping, identity, tmp_path / f"plan-{index}"))
    assert plans[0] == plans[1] and pr.fingerprint(plans[0]) == pr.fingerprint(plans[1])
    assert plans[0]["projection_check"]["status"] == "unavailable"
    assert "source_revision" not in plans[0]["projection_check"]
    assert "automatic command selection" in plans[0]["projection_check"]["reason"]
