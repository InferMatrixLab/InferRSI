from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools import check_evidence_budget as check

LIMIT_FILE = 512 * 1024
LIMIT_PR = 2 * 1024 * 1024


def test_file_under_budget_passes():
    files = [("evidence/campaign_x/summary.json", 100 * 1024, 100 * 1024)]
    violations, total = check.check_file_budgets(
        files, per_file_limit=LIMIT_FILE, per_pr_limit=LIMIT_PR
    )
    assert violations == []
    assert total == 100 * 1024


def test_file_exceeding_budget_fails():
    files = [("evidence/campaign_x/large_trace.parquet", 600 * 1024, 600 * 1024)]
    violations, total = check.check_file_budgets(
        files, per_file_limit=LIMIT_FILE, per_pr_limit=LIMIT_PR
    )
    assert len(violations) == 1
    assert "exceeds per-file limit" in violations[0]
    assert total == 600 * 1024


def test_aggregate_pr_evidence_budget_fails():
    # 5 files added with 450 KiB each = 2,250 KiB (> 2,048 KiB limit), though each file <= 512 KiB
    files = [
        (f"evidence/campaign_x/trace_{i}.json", 450 * 1024, 450 * 1024)
        for i in range(5)
    ]
    violations, total = check.check_file_budgets(
        files, per_file_limit=LIMIT_FILE, per_pr_limit=LIMIT_PR
    )
    assert len(violations) == 1
    assert "exceeds per-PR net limit" in violations[0]
    assert total == 5 * 450 * 1024


def test_modified_file_counts_true_net_addition_not_full_size():
    # A 500 KiB existing file modified with only +10 KiB net growth
    files = [("evidence/campaign_x/existing.json", 500 * 1024, 10 * 1024)]
    violations, total = check.check_file_budgets(
        files, per_file_limit=LIMIT_FILE, per_pr_limit=LIMIT_PR
    )
    assert violations == []
    assert total == 10 * 1024


def test_net_addition_with_deletion_and_shrinkage():
    # Real maintainer scenario: delete 2 MiB, add 5 files of 450 KiB (+2,250 KiB)
    # Net addition is +206,848 bytes, which is well below the 2.0 MiB limit
    files = [
        ("evidence/old_large.bin", 0, -2 * 1024 * 1024),
    ] + [
        (f"evidence/new_{i}.bin", 450 * 1024, 450 * 1024)
        for i in range(5)
    ]
    violations, total = check.check_file_budgets(
        files, per_file_limit=LIMIT_FILE, per_pr_limit=LIMIT_PR
    )
    assert violations == []
    assert total == (5 * 450 * 1024) - (2 * 1024 * 1024)
    assert total == 206848


def test_non_evidence_files_not_counted_in_evidence_budget():
    files = [
        ("src/inferrsi/engine.py", 100 * 1024, 100 * 1024),
        ("tests/test_large.py", 200 * 1024, 200 * 1024),
    ]
    violations, total = check.check_file_budgets(
        files, per_file_limit=LIMIT_FILE, per_pr_limit=LIMIT_PR
    )
    assert violations == []
    assert total == 0


def test_allowlist_bypasses_budget():
    path = "evidence/historical/grandfathered_raw.tar.gz"
    files = [(path, 10 * 1024 * 1024, 10 * 1024 * 1024)]
    violations, total = check.check_file_budgets(
        files,
        per_file_limit=LIMIT_FILE,
        per_pr_limit=LIMIT_PR,
        allowlist={path},
    )
    assert violations == []
    assert total == 0


def test_validate_external_asset_manifest_valid(tmp_path: Path):
    manifest = tmp_path / "inventory.json"
    dummy_sha = "e" * 64
    valid_url = (
        "https://github.com/InferMatrixLab/InferRSI/releases/download/v0.3.0/traces.tar.gz"
    )
    data = {
        "version": 1,
        "bundles": {
            "qwen3-omni-two-gpu": {
                "external_assets": [
                    {
                        "url": valid_url,
                        "sha256": dummy_sha,
                        "bytes": 48920000,
                        "retention_owner": "Dong1017",
                    }
                ]
            }
        },
    }
    manifest.write_text(json.dumps(data), encoding="utf-8")
    errors = check.validate_external_asset_manifest(manifest)
    assert errors == []


def test_validate_external_asset_manifest_rejects_tag_view_url(tmp_path: Path):
    manifest = tmp_path / "inventory_tag.json"
    data = {
        "version": 1,
        "bundles": {
            "tag_bundle": {
                "external_assets": [
                    {
                        "url": "https://github.com/InferMatrixLab/InferRSI/releases/tag/v0.3.0",
                        "sha256": "a" * 64,
                        "bytes": 1000,
                        "retention_owner": "Dong1017",
                    }
                ]
            }
        },
    }
    manifest.write_text(json.dumps(data), encoding="utf-8")
    errors = check.validate_external_asset_manifest(manifest)
    assert len(errors) == 1
    assert "releases/download" in errors[0]
    assert "format check" in errors[0]


def test_validate_external_asset_manifest_rejects_non_list_external_assets(tmp_path: Path):
    manifest = tmp_path / "inventory_dict_assets.json"
    data = {
        "version": 1,
        "bundles": {
            "bad_bundle": {
                "external_assets": {
                    "url": "https://github.com/InferMatrixLab/InferRSI/releases/download/v1/a.bin"
                }
            }
        },
    }
    manifest.write_text(json.dumps(data), encoding="utf-8")
    errors = check.validate_external_asset_manifest(manifest)
    assert len(errors) == 1
    assert "must be a list of asset objects" in errors[0]


def test_validate_external_asset_manifest_rejects_non_dict_bundles(tmp_path: Path):
    manifest = tmp_path / "inventory_bad_bundles.json"
    data = {"version": 1, "bundles": "not_a_dictionary"}
    manifest.write_text(json.dumps(data), encoding="utf-8")
    errors = check.validate_external_asset_manifest(manifest)
    assert len(errors) == 1
    assert "'bundles' must be a JSON object" in errors[0]


def test_validate_external_asset_manifest_rejects_null_fields(tmp_path: Path):
    manifest = tmp_path / "inventory_null_fields.json"
    data = {
        "version": 1,
        "bundles": {
            "null_bundle": {
                "external_assets": [
                    {
                        "url": None,
                        "sha256": None,
                        "bytes": None,
                        "retention_owner": None,
                    }
                ]
            }
        },
    }
    manifest.write_text(json.dumps(data), encoding="utf-8")
    errors = check.validate_external_asset_manifest(manifest)
    assert len(errors) == 4
    assert any("null required field 'url'" in e for e in errors)
    assert any("null required field 'sha256'" in e for e in errors)
    assert any("null required field 'bytes'" in e for e in errors)
    assert any("null required field 'retention_owner'" in e for e in errors)


def test_invalid_base_ref_raises_error(tmp_path: Path):
    with pytest.raises(ValueError, match="cannot be resolved"):
        check.get_changed_files_with_net_sizes("non_existent_ref_12345", repo_root=tmp_path)


def test_git_rename_and_deletion_regression(tmp_path: Path):
    """End-to-end Git test verifying rename, move in/out, delete net delta and non-ASCII paths."""
    repo = tmp_path / "test_repo"
    repo.mkdir()

    def git(*args: str):
        subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)

    git("init", "-b", "main")
    git("config", "user.name", "Tester")
    git("config", "user.email", "tester@example.com")

    # Initial base commit
    ev_dir = repo / "evidence"
    ev_dir.mkdir()
    (ev_dir / "old_600k.bin").write_bytes(b"A" * (600 * 1024))
    (ev_dir / "to_delete_2m.bin").write_bytes(b"B" * (2 * 1024 * 1024))
    (ev_dir / "to_move_out.bin").write_bytes(b"D" * (50 * 1024))
    outside_dir = repo / "outside"
    outside_dir.mkdir()
    (outside_dir / "external.bin").write_bytes(b"C" * (100 * 1024))
    git("add", ".")
    git("commit", "-m", "base commit")

    # Make changes in HEAD:
    # 1. Rename 600 KiB file inside evidence/ -> should trigger per-file limit on dst!
    git("mv", "evidence/old_600k.bin", "evidence/new_600k.bin")

    # 2. Delete 2 MiB file in evidence/ -> should yield -2 MiB delta
    (ev_dir / "to_delete_2m.bin").unlink()
    git("rm", "evidence/to_delete_2m.bin")

    # 3. Add non-ASCII file in evidence/
    (ev_dir / "é_trace.json").write_text('{"status": "ok"}', encoding="utf-8")

    # 4. Move outside file into evidence/ -> +100 KiB net addition
    git("mv", "outside/external.bin", "evidence/external.bin")

    # 5. Move file OUT of evidence/ -> -50 KiB net addition
    git("mv", "evidence/to_move_out.bin", "outside/moved_out.bin")

    git("add", ".")
    git("commit", "-m", "head commit")

    records = check.get_changed_files_with_net_sizes("main~1", repo_root=repo)
    paths = {r[0] for r in records}
    assert "evidence/new_600k.bin" in paths
    assert "evidence/é_trace.json" in paths
    assert "evidence/external.bin" in paths
    assert "evidence/to_move_out.bin" in paths

    # Move out of evidence must record negative delta
    move_out_record = next(r for r in records if r[0] == "evidence/to_move_out.bin")
    assert move_out_record[1] == 0
    assert move_out_record[2] == -(50 * 1024)

    violations, net_bytes = check.check_file_budgets(records)
    # Per-file violation must catch evidence/new_600k.bin
    assert any("evidence/new_600k.bin" in v and "exceeds per-file limit" in v for v in violations)
    # Total net evidence is negative (~ -1.95 MB), so PR net limit is not violated
    assert net_bytes < 0
    assert not any("per-PR net limit" in v for v in violations)


def test_git_symlink_not_measured_as_target_size(tmp_path: Path):
    """Verify symlink blob is measured by its link target text length, not followed."""
    repo = tmp_path / "symlink_repo"
    repo.mkdir()

    def git(*args: str, input_bytes: bytes | None = None):
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            input=input_bytes,
            capture_output=True,
            check=True,
        )

    git("init", "-b", "main")
    git("config", "user.name", "Tester")
    git("config", "user.email", "tester@example.com")

    # Create 600 KiB file outside evidence
    outside_dir = repo / "outside"
    outside_dir.mkdir()
    (outside_dir / "target.bin").write_bytes(b"X" * (600 * 1024))
    git("add", ".")
    git("commit", "-m", "base commit")

    # Create git symlink object pointing to target.bin
    blob_sha = git(
        "hash-object", "-w", "--stdin", input_bytes=b"outside/target.bin"
    ).stdout.decode().strip()
    git("update-index", "--add", "--cacheinfo", "120000", blob_sha, "evidence/symlink.bin")
    git("commit", "-m", "add symlink")

    records = check.get_changed_files_with_net_sizes("main~1", repo_root=repo)
    symlink_record = next(r for r in records if r[0] == "evidence/symlink.bin")
    # Blob size of 'outside/target.bin' is 18 bytes, NOT 600 KiB
    assert symlink_record[1] == len("outside/target.bin")
    violations, _ = check.check_file_budgets(records)
    assert violations == []


def test_git_empty_blob_with_dirty_worktree_not_misreported(tmp_path: Path):
    """Verify empty blob committed in HEAD is not inflated by dirty uncommitted worktree."""
    repo = tmp_path / "empty_blob_repo"
    repo.mkdir()

    def git(*args: str):
        subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)

    git("init", "-b", "main")
    git("config", "user.name", "Tester")
    git("config", "user.email", "tester@example.com")
    (repo / "README.md").write_text("# Base")
    git("add", ".")
    git("commit", "-m", "base")

    # In HEAD commit, commit an empty file in evidence/
    ev_dir = repo / "evidence"
    ev_dir.mkdir()
    empty_file = ev_dir / "empty.bin"
    empty_file.write_bytes(b"")
    git("add", ".")
    git("commit", "-m", "add empty file")

    # Now write 600 KiB dirty worktree content without committing
    empty_file.write_bytes(b"Z" * (600 * 1024))

    records = check.get_changed_files_with_net_sizes("main~1", repo_root=repo)
    empty_record = next(r for r in records if r[0] == "evidence/empty.bin")
    # Committed blob in HEAD is 0 bytes, not 600 KiB
    assert empty_record[1] == 0
    assert empty_record[2] == 0

    violations, net_bytes = check.check_file_budgets(records)
    assert violations == []
    assert net_bytes == 0


def test_local_mode_untracked_files_expanded(tmp_path: Path):
    """Verify local mode without base ref expands untracked nested directories."""
    repo = tmp_path / "local_repo"
    repo.mkdir()

    def git(*args: str):
        subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)

    git("init", "-b", "main")
    git("config", "user.name", "Tester")
    git("config", "user.email", "tester@example.com")
    (repo / "README.md").write_text("# Repo")
    git("add", ".")
    git("commit", "-m", "init")

    # Add untracked deep nested file exceeding per-file limit
    deep_dir = repo / "evidence" / "nested" / "run_01"
    deep_dir.mkdir(parents=True)
    (deep_dir / "large_raw.bin").write_bytes(b"Z" * (600 * 1024))

    records = check.get_changed_files_with_net_sizes(base_ref=None, repo_root=repo)
    matching = [r for r in records if "evidence/nested/run_01/large_raw.bin" in r[0]]
    assert len(matching) == 1
    assert matching[0][1] == 600 * 1024

    violations, _ = check.check_file_budgets(records)
    assert any("large_raw.bin" in v and "exceeds per-file limit" in v for v in violations)


def test_main_negative_case_fails_without_report_only(tmp_path: Path, monkeypatch, capsys):
    """Negative case: candidate budget violation without --report-only exits with code 1."""
    monkeypatch.setattr(check, "ROOT", tmp_path)
    ev_dir = tmp_path / "evidence"
    ev_dir.mkdir()
    ev_file = ev_dir / "large_raw.bin"
    ev_file.write_bytes(b"A" * (600 * 1024))

    monkeypatch.setattr(
        "sys.argv",
        [
            "check_evidence_budget.py",
            "--files",
            str(ev_file),
            "--max-file-bytes",
            str(512 * 1024),
            "--inventory",
            "nonexistent_inv.json",
        ],
    )
    rc = check.main()
    captured = capsys.readouterr()
    assert rc == 1
    assert "exceeds per-file limit" in captured.out
    assert "Candidate evidence byte budget exceeded" in captured.out
    assert "Running in report-only mode" not in captured.out


def test_main_report_only_mode_warns_and_exits_zero(tmp_path: Path, monkeypatch, capsys):
    """Report-only mode: candidate budget violation warns but exits 0 pending #273 acceptance."""
    monkeypatch.setattr(check, "ROOT", tmp_path)
    ev_dir = tmp_path / "evidence"
    ev_dir.mkdir()
    ev_file = ev_dir / "candidate_large.bin"
    ev_file.write_bytes(b"B" * (600 * 1024))

    monkeypatch.setattr(
        "sys.argv",
        [
            "check_evidence_budget.py",
            "--files",
            str(ev_file),
            "--max-file-bytes",
            str(512 * 1024),
            "--report-only",
            "--inventory",
            "nonexistent_inv.json",
        ],
    )
    rc = check.main()
    captured = capsys.readouterr()
    assert rc == 0
    assert "exceeds per-file limit" in captured.out
    assert "Running in report-only mode" in captured.out
    assert "Refs #273" in captured.out


def test_validate_external_asset_manifest_explicit_format_check_diagnostic(tmp_path: Path):
    """External asset manifest URL diagnostic explicitly identifies validation as a format check."""
    manifest = tmp_path / "invalid_manifest.json"
    data = {
        "bundles": {
            "test_bundle": {
                "external_assets": [
                    {
                        "url": "https://example.com/asset.zip",
                        "sha256": "0" * 64,
                        "bytes": 1024,
                        "retention_owner": "maintainer",
                    }
                ]
            }
        }
    }
    manifest.write_text(json.dumps(data), encoding="utf-8")
    errors = check.validate_external_asset_manifest(manifest)
    assert len(errors) == 1
    assert "url format check failed" in errors[0]
    assert "format check only; does not verify downloadability or remote hash" in errors[0]


def test_main_cli_help_mentions_format_check_and_report_only(monkeypatch, capsys):
    """CLI help output explicitly mentions format check and --report-only mode."""
    monkeypatch.setattr("sys.argv", ["check_evidence_budget.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        check.main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "format check" in captured.out
    assert "--report-only" in captured.out

