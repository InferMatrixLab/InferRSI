from __future__ import annotations

import json
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
    # Total net evidence addition is 10 KiB, not 500 KiB
    assert total == 10 * 1024


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


def test_invalid_base_ref_raises_error(tmp_path: Path):
    with pytest.raises(ValueError, match="cannot be resolved"):
        check.get_changed_files_with_net_sizes("non_existent_ref_12345", repo_root=tmp_path)
