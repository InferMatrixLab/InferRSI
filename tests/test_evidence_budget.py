from __future__ import annotations

import json
from pathlib import Path

from tools import check_evidence_budget as check

LIMIT_FILE = 512 * 1024
LIMIT_PR = 2 * 1024 * 1024


def test_file_under_budget_passes():
    files = [("evidence/campaign_x/summary.json", 100 * 1024)]
    violations, total = check.check_file_budgets(
        files, per_file_limit=LIMIT_FILE, per_pr_limit=LIMIT_PR
    )
    assert violations == []
    assert total == 100 * 1024


def test_file_exceeding_budget_fails():
    files = [("evidence/campaign_x/large_trace.parquet", 600 * 1024)]
    violations, total = check.check_file_budgets(
        files, per_file_limit=LIMIT_FILE, per_pr_limit=LIMIT_PR
    )
    assert len(violations) == 1
    assert "exceeds limit" in violations[0]
    assert total == 600 * 1024


def test_aggregate_pr_evidence_budget_fails():
    # 5 files of 450 KiB each = 2,250 KiB (> 2,048 KiB limit), though each file <= 512 KiB
    files = [
        (f"evidence/campaign_x/trace_{i}.json", 450 * 1024)
        for i in range(5)
    ]
    violations, total = check.check_file_budgets(
        files, per_file_limit=LIMIT_FILE, per_pr_limit=LIMIT_PR
    )
    assert len(violations) == 1
    assert "exceeds per-PR limit" in violations[0]
    assert total == 5 * 450 * 1024


def test_non_evidence_files_not_counted_in_evidence_budget():
    files = [
        ("src/inferrsi/engine.py", 100 * 1024),
        ("tests/test_large.py", 200 * 1024),
    ]
    violations, total = check.check_file_budgets(
        files, per_file_limit=LIMIT_FILE, per_pr_limit=LIMIT_PR
    )
    assert violations == []
    assert total == 0


def test_allowlist_bypasses_budget():
    path = "evidence/historical/grandfathered_raw.tar.gz"
    files = [(path, 10 * 1024 * 1024)]
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
    data = {
        "version": 1,
        "bundles": {
            "qwen3-omni-two-gpu": {
                "external_assets": [
                    {
                        "url": "https://github.com/InferMatrixLab/InferRSI/releases/tag/v0.3.0",
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


def test_validate_external_asset_manifest_missing_and_invalid(tmp_path: Path):
    manifest = tmp_path / "inventory_invalid.json"
    data = {
        "version": 1,
        "bundles": {
            "bad_bundle": {
                "external_assets": [
                    {
                        "url": "http://insecure.site/trace.bin",
                        "sha256": "bad_sha",
                        "bytes": -5,
                        "retention_owner": "",
                    }
                ]
            }
        },
    }
    manifest.write_text(json.dumps(data), encoding="utf-8")
    errors = check.validate_external_asset_manifest(manifest)
    assert len(errors) == 4
    assert any("https URL" in e for e in errors)
    assert any("invalid sha256" in e for e in errors)
    assert any("positive integer" in e for e in errors)
    assert any("retention_owner must be non-empty" in e for e in errors)
