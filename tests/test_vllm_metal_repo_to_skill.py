"""Source-derived operating graph integrity and offline helper contracts."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import runpy
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
import yaml

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT / "src/inferrsi/data/skill_library/repositories/vllm-metal"
CASES = PROJECT / "tests/fixtures/repo_to_skill/vllm-metal/test-cases"


def helper(area, name):
    return runpy.run_path(str(ROOT / "sub-skills" / area / "scripts" / name))


def test_vllm_metal_graph_is_contained_candidate_with_exact_source_scope():
    paths = list(ROOT.rglob("SKILL.md"))
    assert len(paths) == 4
    for path in paths:
        header = path.read_text().split("---", 2)[1]
        value = yaml.safe_load(header)
        assert value["name"] == path.parent.name
        assert value["license"] == "NO_LICENSE"
        assert value["disable-model-invocation"] is True
        assert value["metadata"]["disco-role"] == "operating"
        assert re.search(r'^description: ".+"$', header, re.MULTILINE)
    for path in ROOT.rglob("*.md"):
        text = path.read_text()
        assert "/workspace/" not in text and "/home/agent/" not in text
        for target in re.findall(r"\]\(([^)]+)\)", text):
            link = urlsplit(target)
            if link.scheme or not link.path:
                continue
            resolved = (path.parent / unquote(link.path)).resolve()
            assert resolved.is_relative_to(ROOT.resolve()) and resolved.is_file(), (path, target)
    metadata = json.loads((ROOT / "metadata.json").read_text())
    assert metadata["status"] == "candidate"
    assert metadata["empirical_validation"] == "partial_cpu_only"
    assert metadata["construction"]["native_import"] == "not-run"
    assert "BLOCKED_REQUIRED_BACKEND" in " ".join(metadata["limitations"])
    source = json.loads((ROOT / "references/source-identity.json").read_text())
    assert source["source_commit"] == metadata["sources"][0]["commit"]
    assert len(source["files"]) == 38
    assert set(source["files"]) == set(source["inspected_sections"])
    assert all(re.fullmatch(r"[a-f0-9]{64}", value) for value in source["files"].values())
    assert hashlib.sha256((ROOT / "LICENSE").read_bytes()).hexdigest() == source["files"]["LICENSE"]
    assert not list(ROOT.rglob("__pycache__"))


def test_vllm_metal_cases_cover_every_route_and_integrated_failures():
    paths = list(CASES.rglob("assertions.json"))
    assert len(paths) == 10
    assert len(list((CASES / "integration").glob("*/assertions.json"))) == 2
    for area in ("platform-config", "cache-lifecycle", "qualification"):
        assert len(list((CASES / "sub-skills" / area).glob("*/assertions.json"))) == 2
    for path in paths:
        value = json.loads(path.read_text())
        assert value["schema"] == "disco.usability-case.v1"
        assert value["assertions"] and value["evidence_basis"]
        assert (path.parent / "user_request.txt").read_text().strip()
        for relative in value["expected_skill_files"]:
            resolved = (ROOT / relative).resolve()
            assert resolved.is_relative_to(ROOT.resolve()) and resolved.is_file()


@pytest.mark.parametrize("values,n_errors", [
    ({}, 0),
    ({"VLLM_METAL_BACKEND": "mps", "VLLM_METAL_SPEC_INGEST_CHUNK": "0"}, 0),
    ({"VLLM_MLX_DEVICE": "GPU", "VLLM_METAL_SPEC_INGEST_CHUNK": "1k"}, 2),
    ({"VLLM_METAL_RING_BASE_PORT": "65536"}, 1),
    ({"VLLM_METAL_TQ_PREFILL_MAX_MIB": "64MiB"}, 1),
    ({"VLLM_METAL_TQ_PREFILL_MAX_MIB": "0"}, 0),
    ({"VLLM_METAL_TQ_PREFILL_MAX_MIB": "-1"}, 1),
])
def test_selected_environment_syntax_not_compatibility(values, n_errors):
    result = helper("platform-config", "check_environment_plan.py")["check"](values)
    assert len(result["errors"]) == n_errors
    assert result["native_verification"] == "not_run"
    assert result["feature_compatibility"] == "not_verified"
    assert result["parsed"]["VLLM_METAL_MM_PREFIX_PATH"] is None


def test_boolean_non_one_is_off_and_nonstring_unknown_plans_fail():
    check = helper("platform-config", "check_environment_plan.py")["check"]
    result = check({"VLLM_METAL_BUILD_FROM_SOURCE": "yes"})
    assert not result["parsed"]["VLLM_METAL_BUILD_FROM_SOURCE"]
    assert not result["errors"] and result["warnings"]
    for value in ([], {"unknown": "1"}, {"VLLM_MLX_DEVICE": True}):
        with pytest.raises(ValueError):
            check(value)


def test_dense_pool_floor_and_explicit_cache_are_not_fit_evidence():
    module = helper("cache-lifecycle", "screen_pool_budget.py")
    plan = module["example"]()
    result = module["screen"](plan)
    assert result["per_token_bytes"] == 1024
    assert result["per_block_bytes"] == 16384
    assert result["reserved_request_plus_null_block_bytes"] == 49152
    plan.update(kv_budget_bytes=65536, blocks_per_chunk=2)
    result = module["screen"](plan)
    assert result["selected_pool_bytes"] == 32768
    assert result["remaining_cache_budget_bytes"] == 32768
    assert "offload_leaves_no_room_for_one_request_and_null_block" in result["problems"]
    plan = module["example"]()
    plan["budget_mode"] = "explicit-cache"
    result = module["screen"](plan)
    assert result["physical_cache_plus_pool_capacity_bytes"] == 1114112
    assert result["reserved_request_plus_null_block_bytes"] == 0
    assert result["physical_fit"] == result["runtime_eligibility"] == "not_verified"
    plan["layout"] = "hybrid"
    with pytest.raises(ValueError):
        module["screen"](plan)


def record():
    def row(variant, phase, execution, tokens, duration):
        return dict(variant=variant, phase=phase, execution=execution,
                    output_tokens=tokens, duration_ms=duration)
    return {
        "schema_version": 1, "source_commit": "a" * 40, "controls_sha256": "b" * 64,
        "metric": "http-serving",
        "samples": [row("baseline", "warmup", "completed", 8, 100),
                    row("baseline", "measured", "completed", 10, 1000),
                    row("candidate", "measured", "blocked", None, None)],
    }


def test_completed_subset_accounting_preserves_blocked_arm():
    summarize = helper("qualification", "summarize_serving_records.py")["summarize"]
    result = summarize(record())
    assert result["variants"]["baseline"]["completed_subset_tokens_per_second"] == 10
    assert result["variants"]["baseline"]["warmup_records_excluded"] == 1
    candidate = result["variants"]["candidate"]
    assert candidate["execution_counts"] == {"blocked": 1}
    assert candidate["completed_subset_tokens_per_second"] is None
    assert result["evidence_state"] == "INCONCLUSIVE"
    assert "speedup" not in result and "verdict" not in result


@pytest.mark.parametrize("mutation", [
    {"schema_version": True}, {"source_commit": "main"}, {"controls_sha256": "nohash"},
    {"metric": "tokens-from-chars"}, {"samples": []},
])
def test_record_identity_and_scope_syntax_rejection(mutation):
    value = record()
    value.update(mutation)
    with pytest.raises(ValueError):
        helper("qualification", "summarize_serving_records.py")["summarize"](value)


@pytest.mark.parametrize("field,value", [
    ("output_tokens", True), ("output_tokens", -1), ("output_tokens", 1.5),
    ("duration_ms", 0), ("duration_ms", float("nan")), ("duration_ms", float("inf")),
])
def test_record_invalid_measurements(field, value):
    data = copy.deepcopy(record())
    data["samples"][1][field] = value
    with pytest.raises(ValueError):
        helper("qualification", "summarize_serving_records.py")["summarize"](data)


def test_all_helpers_help_and_cli_rejection_are_bounded(tmp_path):
    scripts = sorted(ROOT.rglob("scripts/*.py"))
    assert len(scripts) == 3
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"schema_version":1,"schema_version":2}')
    for script in scripts:
        result = subprocess.run([sys.executable, str(script), "--help"], cwd=tmp_path,
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 0
        result = subprocess.run([sys.executable, str(script), str(invalid)], cwd=tmp_path,
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 2 and "Traceback" not in result.stderr
