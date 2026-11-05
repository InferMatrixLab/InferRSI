"""Real Git fixtures exercise path coverage and current-head declaration safety."""

import json
import subprocess
from pathlib import Path

import pytest

from tools import check_knowledge_model_policy as checker
from tools import knowledge_contribution as helper

ROOT = Path(__file__).resolve().parents[1]
SKILL = "src/inferrsi/data/skill_library/methods/example/SKILL.md"
GENERATED = helper.GENERATED + "common/skills/example.json"
HUMAN = {"human_only": True, "material_ai_authors": []}
AI = {"human_only": False, "material_ai_authors": [
    {"tool": "example-agent", "model_id": "unknown", "effort": "unknown", "role": "author"},
]}


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                          check=True).stdout.decode().strip()


def write(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def commit(root):
    git(root, "add", "--all")
    git(root, "commit", "-qm", "Fixture change")
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Example Contributor")
    git(tmp_path, "config", "user.email", "contributor@example.com")
    git(tmp_path, "config", "core.autocrlf", "false")
    write(tmp_path, helper.POLICY, (ROOT / helper.POLICY).read_text(encoding="utf-8"))
    write(tmp_path, SKILL, "original skill\n")
    write(tmp_path, GENERATED, '{"original": true}\n')
    write(tmp_path, "delete.txt", "remove me\n")
    return tmp_path, commit(tmp_path)


def test_complete_paths_renames_deletions_generated_and_escaping(repo):
    root, base = repo
    renamed = SKILL.replace("example", 'tab\tquote"line\nexample')
    (root / renamed).parent.mkdir(parents=True)
    (root / SKILL).rename(root / renamed)
    (root / "delete.txt").unlink()
    write(root, GENERATED, '{"changed": true}\n')
    write(root, "plain.txt", "substantive\n")
    head = commit(root)
    report = helper.contribution_report(root, base)
    expected = sorted([SKILL, renamed, GENERATED, "delete.txt", "plain.txt"])
    assert report["changed_paths"] == expected
    assert report["protected_paths"] == sorted([SKILL, renamed, GENERATED])
    assert report["exception_paths"] == report["protected_paths"]
    assert report["generated_paths"] == [GENERATED]
    assert report["substantive_paths"] == sorted([SKILL, renamed, "delete.txt", "plain.txt"])
    assert report["head_sha"] == head
    assert report["base_sha"] == report["policy_sha"] == report["merge_base_sha"] == base
    assert report["dirty_paths"] == []
    assert "declaration" not in report
    serialized = json.dumps(report, ensure_ascii=True)
    assert json.loads(serialized)["changed_paths"] == expected
    block = helper.declaration_block(root, report, AI, 'explicit reason\n```\n"quoted"')
    declaration = checker.declaration(block, head)
    assert declaration["exception"]["paths"] == report["protected_paths"]
    assert declaration["material_ai_authors"] == AI["material_ai_authors"]
    policy = json.loads((root / helper.POLICY).read_text())
    assessment = checker.assess({"number": 1, "head": {"sha": head}, "body": block},
                                expected, policy)
    assert assessment["state"] == "failure"  # A generated request never grants approval.


def test_reads_policy_from_explicit_base_not_head_or_worktree(repo):
    root, base = repo
    write(root, SKILL, "changed\n")
    policy = json.loads((root / helper.POLICY).read_text())
    policy["protected_paths"] = []
    write(root, helper.POLICY, json.dumps(policy))
    commit(root)
    write(root, helper.POLICY, "not JSON")
    report = helper.contribution_report(root, base)
    assert report["protected_paths"] == [SKILL]
    assert report["policy_paths"] == [helper.POLICY]
    assert report["dirty_paths"] == [helper.POLICY]


def test_pr_diff_uses_merge_base_but_policy_uses_target_tip(repo):
    root, base = repo
    git(root, "checkout", "-qb", "target")
    policy = json.loads((root / helper.POLICY).read_text())
    policy["protected_paths"].append("new-protected.txt")
    write(root, helper.POLICY, json.dumps(policy))
    write(root, "target-only.txt", "target change\n")
    tip = commit(root)
    git(root, "checkout", "-qb", "candidate", base)
    write(root, "new-protected.txt", "candidate change\n")
    head = commit(root)
    report = helper.contribution_report(root, "target")
    assert report["changed_paths"] == report["protected_paths"] == ["new-protected.txt"]
    assert report["policy_sha"] == tip
    assert report["merge_base_sha"] == base
    assert report["head_sha"] == head


@pytest.mark.parametrize("state", ["unstaged", "staged", "untracked", "staged-restored"])
def test_dirty_paths_reported_but_never_certified(repo, state):
    root, base = repo
    path = "untracked.txt" if state == "untracked" else SKILL
    write(root, path, "changed\n")
    if state in {"staged", "staged-restored"}:
        git(root, "add", path)
    if state == "staged-restored":
        write(root, path, "original skill\n")
    report = helper.contribution_report(root, base)
    assert report["changed_paths"] == []
    assert report["dirty_paths"] == [path]
    with pytest.raises(ValueError, match="local changes"):
        helper.declaration_block(root, report, HUMAN)


def test_rechecks_head_and_dirty_state_before_declaration(repo):
    root, base = repo
    report = helper.contribution_report(root, base)
    write(root, SKILL, "new changes\n")
    with pytest.raises(ValueError, match="local changes"):
        helper.declaration_block(root, report, HUMAN)
    commit(root)
    with pytest.raises(ValueError):
        helper.declaration_block(root, report, HUMAN)


def test_head_move_during_report_fails(repo, monkeypatch):
    root, base = repo
    original = helper._dirty_paths

    def changed(project, head):
        result = original(project, head)
        git(root, "commit", "--allow-empty", "-qm", "Advance fixture")
        return result

    monkeypatch.setattr(helper, "_dirty_paths", changed)
    with pytest.raises(ValueError, match="HEAD changed"):
        helper.contribution_report(root, base)


def test_truthful_unknowns_preserved_and_human_only_must_be_explicit(repo):
    root, base = repo
    report = helper.contribution_report(root, base)
    for facts in (HUMAN, AI):
        block = helper.declaration_block(root, report, facts)
        parsed = checker.declaration(block, base)
        assert parsed == {"schema_version": 1, "head_sha": base, **facts}
        assert "exception" not in parsed
    for facts in ({}, {"material_ai_authors": []},
                  {"human_only": True, "material_ai_authors": AI["material_ai_authors"]},
                  {**AI, "exception": {"reason": "injected"}},
                  {**AI, "head_sha": "0" * 40}):
        with pytest.raises(ValueError):
            helper.declaration_block(root, report, facts)


def test_exception_requires_explicit_reason_and_protected_paths(repo):
    root, base = repo
    report = helper.contribution_report(root, base)
    for reason in ("", " ", "no protected paths"):
        with pytest.raises(ValueError):
            helper.declaration_block(root, report, AI, reason)


def test_cli_report_and_explicit_declaration(repo, tmp_path, monkeypatch, capsys):
    root, base = repo
    monkeypatch.setattr(helper, "PROJECT", root)
    assert helper.main(["--base", base]) == 0
    assert json.loads(capsys.readouterr().out)["head_sha"] == base
    facts = tmp_path.parent / f"{tmp_path.name}-authors.json"
    facts.write_text(json.dumps(AI))
    assert helper.main(["--base", base, "--authors-file", str(facts)]) == 0
    assert checker.declaration(capsys.readouterr().out, base)["material_ai_authors"] == (
        AI["material_ai_authors"]
    )
    facts.write_text('{"human_only":true,"human_only":false,"material_ai_authors":[]}')
    assert helper.main(["--base", base, "--authors-file", str(facts)]) == 1
    captured = capsys.readouterr()
    assert not captured.out
    assert "Duplicate JSON field" in captured.err
    assert helper.main(["--base=--bad-ref"]) != 0


def test_deleted_generated_paths_remain_in_exception_scope(repo):
    root, base = repo
    (root / GENERATED).unlink()
    commit(root)
    report = helper.contribution_report(root, base)
    assert report["changed_paths"] == report["generated_paths"] == [GENERATED]
    assert report["protected_paths"] == report["exception_paths"] == [GENERATED]
    assert report["substantive_paths"] == []


def test_generated_only_unknown_authorship_is_not_exempt(repo):
    root, base = repo
    write(root, GENERATED, "changed generated index")
    head = commit(root)
    report = helper.contribution_report(root, base)
    block = helper.declaration_block(root, report, AI)
    policy = json.loads((root / helper.POLICY).read_text())
    result = checker.assess({"number": 1, "head": {"sha": head}, "body": block},
                            report["changed_paths"], policy)
    assert result["state"] == "failure"
    assert result["errors"] == ["Material AI author 1: model is unapproved or suspended"]


def test_backslash_path_reported_without_hiding_checker_scope_restriction(repo):
    root, base = repo
    path = SKILL.replace("example", "back\\slash")
    write(root, path, "changed skill")
    commit(root)
    report = helper.contribution_report(root, base)
    assert report["protected_paths"] == [path]
    with pytest.raises(ValueError, match="POSIX"):
        helper.declaration_block(root, report, AI, "explicit exception request")


@pytest.mark.parametrize("raw", ["null", "[]", '{"schema_version":true}',
                                '{"schema_version":1,"protected_paths":"**"}',
                                '{"schema_version":1,"schema_version":1}'])
def test_malformed_trusted_policy_fails(repo, raw):
    root, _ = repo
    write(root, helper.POLICY, raw)
    base = commit(root)
    with pytest.raises(ValueError):
        helper.contribution_report(root, base)


def test_cli_requires_explicit_base_and_authors_for_exception(capsys):
    for args in ([], ["--base", "HEAD", "--exception-reason", "reason"]):
        with pytest.raises(SystemExit) as raised:
            helper.main(args)
        assert raised.value.code == 2
        assert not capsys.readouterr().out


@pytest.mark.parametrize("deleted", [False, True])
def test_skill_coverage_classified_as_generated_without_classifying_other_docs(repo, deleted):
    root, _ = repo
    coverage = "docs/skill-coverage.md"
    other = "docs/example.md"
    write(root, coverage, "original coverage\n")
    write(root, other, "original documentation\n")
    base = commit(root)
    if deleted:
        (root / coverage).unlink()
    else:
        write(root, coverage, "updated generated coverage\n")
    write(root, other, "updated documentation\n")
    commit(root)
    report = helper.contribution_report(root, base)
    assert report["changed_paths"] == sorted([coverage, other])
    assert report["generated_paths"] == [coverage]
    assert report["substantive_paths"] == [other]
    policy = json.loads((root / helper.POLICY).read_text())
    assert report["protected_paths"] == sorted(checker.matching(
        [coverage, other], policy["protected_paths"],
    ))
    assert report["exception_paths"] == report["protected_paths"]
