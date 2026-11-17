import json
import subprocess

from tools import knowledge_declaration_paths as helper

POLICY = {
    "protected_paths": [
        "src/inferrsi/knowledge/data/skill_library/**",
        "src/inferrsi/knowledge/data/repo_packs/**/knowledge/**",
        "docs/reference-matrix.md",
    ],
    "policy_paths": [".github/knowledge-model-policy.json"],
}
LIBRARY = "src/inferrsi/knowledge/data/skill_library"
SKILL = f"{LIBRARY}/methods/a/SKILL.md"
MOVED = f"{LIBRARY}/methods/b/old.md"
RECORD = (
    "src/inferrsi/knowledge/data/repo_packs/inferrsi/knowledge/common/skills/c.json"
)


def _git(root, *args):
    return subprocess.run(
        ["git", "-c", "user.name=Helper fixture", "-c", "user.email=fixture@example.invalid",
         "-c", "commit.gpgsign=false", *args], cwd=root, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _write(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def test_reports_every_protected_path_including_deletions_and_renames(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    _write(tmp_path, helper.POLICY, json.dumps(POLICY))
    _write(tmp_path, SKILL, "a\n" * 20)
    _write(tmp_path, MOVED, "b\n" * 20)
    _write(tmp_path, RECORD, "{}\n")
    _write(tmp_path, "README.md", "readme\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    _git(tmp_path, "switch", "-q", "-c", "contribution")
    _write(tmp_path, SKILL, "a\n" * 20 + "more\n")
    (tmp_path / "docs").mkdir()
    _git(tmp_path, "mv", MOVED, "docs/moved.md")
    _git(tmp_path, "rm", "-q", RECORD)
    _write(tmp_path, "README.md", "changed\n")
    # A PR cannot widen or narrow its own admission scope by editing its policy copy.
    _write(tmp_path, helper.POLICY, json.dumps({**POLICY, "protected_paths": []}))
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "contribution")

    result = helper.report(tmp_path, base, "HEAD")
    protected = [
        RECORD,
        SKILL,
        MOVED,
    ]
    assert result["head_sha"] == _git(tmp_path, "rev-parse", "HEAD")
    assert result["protected_paths"] == result["exception_scope"] == protected
    assert result["policy_paths"] == [helper.POLICY]
    assert result["generated_paths"] == [protected[0]]
    assert result["other_paths"] == ["README.md", "docs/moved.md"]
    assert result["declaration_required"] is True
    assert "material_ai_authors" not in result and "model_id" not in json.dumps(result)


def test_unprotected_change_needs_no_declaration(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    _write(tmp_path, helper.POLICY, json.dumps(POLICY))
    _write(tmp_path, "README.md", "readme\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    _write(tmp_path, "README.md", "changed\n")
    _git(tmp_path, "commit", "-q", "-am", "docs")
    result = helper.report(tmp_path, base, "HEAD")
    assert result["protected_paths"] == [] and result["declaration_required"] is False
    assert result["other_paths"] == ["README.md"]
