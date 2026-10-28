"""Candidate graph integrity and declaration-only helpers, not Metal qualification."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import runpy
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
import yaml

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT / "src/inferrsi/data/skill_library/repositories/mistral-rs"
CASES = PROJECT / "tests/fixtures/repo_to_skill/mistral-rs/test-cases"
SCRIPTS = {
    "decode-contract": "audit_decode_metadata.py",
    "prefill-contract": "screen_prefill_metadata.py",
    "qualification": "warmup_shape_inventory.py",
}


def helper(area):
    return runpy.run_path(str(ROOT / "sub-skills" / area / "scripts" / SCRIPTS[area]))


def call_cli(area, *args, data=None, cwd=None):
    script = ROOT / "sub-skills" / area / "scripts" / SCRIPTS[area]
    return subprocess.run(
        [sys.executable, str(script), *args], input=data, capture_output=True,
        timeout=10, cwd=cwd, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def test_mistral_rs_graph_is_contained_candidate_with_exact_source_scope():
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
    assert metadata["empirical_validation"] == "not_run"
    assert metadata["construction"]["native_import"] == "not-run"
    assert "BLOCKED_REQUIRED_BACKEND" in " ".join(metadata["limitations"])
    source = json.loads((ROOT / "references/source-identity.json").read_text())
    assert source["source_commit"] == metadata["sources"][0]["commit"]
    assert source["source_commit"] == "9459891e7697238225885518119682ac8209a612"
    assert len(source["files"]) == 24
    assert set(source["files"]) == set(source["inspected_sections"])
    assert set(source["files"]) == set(metadata["sources"][0]["paths"])
    assert all(re.fullmatch(r"[a-f0-9]{64}", value) for value in source["files"].values())
    retained = {
        "LICENSE": "LICENSE",
        "references/apache-component-license.md": "mistralrs-paged-attn/LICENSE-APACHE",
        "references/paged-component-notice.md": "mistralrs-paged-attn/NOTICE",
    }
    for local, original in retained.items():
        assert hashlib.sha256((ROOT / local).read_bytes()).hexdigest() == source["files"][original]
    assert not list(ROOT.rglob("__pycache__"))
    assert not list(ROOT.rglob("assertions.json"))


def test_mistral_rs_cases_cover_every_route_and_integrated_failures():
    paths = list(CASES.rglob("assertions.json"))
    assert len(paths) == 10
    assert len(list((CASES / "root").glob("*/assertions.json"))) == 2
    assert len(list((CASES / "integration").glob("*/assertions.json"))) == 2
    for area in SCRIPTS:
        assert len(list((CASES / "sub-skills" / area).glob("*/assertions.json"))) == 2
    for path in paths:
        value = json.loads(path.read_text())
        assert value["schema"] == "disco.usability-case.v1"
        assert value["assertions"] and value["evidence_basis"]
        assert (path.parent / "user_request.txt").read_text().strip()
        assert (path.parent / "README.md").read_text().strip()
        for relative in value["expected_skill_files"]:
            resolved = (ROOT / relative).resolve()
            assert resolved.is_relative_to(ROOT.resolve()) and resolved.is_file()


def test_prefill_example_is_byte_screening_not_fit_or_gpu_evidence():
    module = helper("prefill-contract")
    result = module["screen"](module["example"]())
    assert result["expected_query_shape"] == [1, 4, 8, 64]
    assert result["storage_rows"] == 8
    assert result["output_raw_bytes"] == 6144
    assert result["metadata_raw_bytes"] == 160
    assert result["output_allocation_bytes"] == result["metadata_reservation_bytes"] == 16384
    assert result["workspace_formula_bytes"] == 32768
    assert result["query_copy_if_needed_bytes_additional"] == 16384
    assert result["output_copy_if_needed_bytes_additional"] == 16384
    assert result["minimum_table_columns"] == 10  # Non-power-of-two block size 7.
    assert result["metadata_binding"] == "inline"
    assert result["native_verification"] == result["compiler_check"] == "not_run"
    assert result["runtime_eligibility"] == result["numerical_correctness"] == "not_verified"


def test_prefill_mask_offsets_use_max_extent_69_not_summed_packed_contexts():
    module = helper("prefill-contract")
    plan = module["example"]()
    plan.update(mask_key_offsets=[4, 4], additive_mask_shape=[1, 4, 8, 69])
    assert module["screen"](plan)["expected_mask_extents"] == [1, 4, 8, 69]
    plan["additive_mask_shape"][-1] = 68
    with pytest.raises(ValueError, match="broadcast extents"):
        module["screen"](plan)
    plan["additive_mask_shape"] = [8, 70]  # Rank-2 Q/K with broadcast batch/head.
    assert module["screen"](plan)["expected_mask_extents"][-1] == 69
    plan["mask_key_offsets"] = None
    plan["additive_mask_shape"] = [1, 4, 8, 82]
    assert module["screen"](plan)["expected_mask_extents"][-1] == 82


def test_prefill_packed_queries_and_mask_are_independent_declarations():
    module = helper("prefill-contract")
    plan = module["example"]()
    plan.update(packed_queries=False, packed_mask=False, additive_mask_shape=None)
    result = module["screen"](plan)
    assert result["storage_rows"] == 10
    assert result["expected_query_shape"] == [2, 4, 5, 64]
    assert result["expected_mask_extents"] == [2, 4, 5, 65]
    assert result["output_raw_bytes"] == 7680
    plan["packed_mask"] = True
    result = module["screen"](plan)
    assert result["storage_rows"] == 10 and result["expected_mask_extents"] == [1, 4, 8, 82]


@pytest.mark.parametrize("batch,binding,raw", [(56, "inline", 4032), (57, "buffered", 4104)])
def test_prefill_metadata_inline_boundary_still_reserves_workspace(batch, binding, raw):
    module = helper("prefill-contract")
    plan = module["example"]()
    plan.update(query_lens=[1] * batch, context_lens=[1] * batch,
                query_start_positions=[0] * batch, key_start_positions=[0] * batch,
                multimodal_ranges=[[] for _ in range(batch)], additive_mask_shape=None)
    result = module["screen"](plan)
    assert result["metadata_binding"] == binding and result["metadata_raw_bytes"] == raw
    assert result["metadata_reservation_bytes"] == 16384


@pytest.mark.parametrize("mutation", [
    {"schema_version": True}, {"unknown": 1}, {"packed_queries": 1},
    {"query_lens": []}, {"context_lens": [1]}, {"query_lens": [True, 5]},
    {"num_heads": 3}, {"key_head_dim": 4097}, {"cache_dtype": "int8"},
    {"mask_key_offsets": [0]}, {"multimodal_ranges": [[], [[5, 5]]]},
    {"sliding_window": 0}, {"additive_mask_shape": [2, 4, 8, 82]},
])
def test_prefill_invalid_declarations_raise_without_native_execution(mutation):
    module = helper("prefill-contract")
    plan = module["example"]()
    plan.update(copy.deepcopy(mutation))
    with pytest.raises(ValueError):
        module["screen"](plan)


@pytest.mark.parametrize("mutation", [
    {"query_start_positions": [(1 << 64) - 2, 149]},
    {"key_start_positions": [(1 << 64) - 1, 96]},
    {"mask_key_offsets": [(1 << 64) - 1, 0]},
    {"num_heads": (1 << 64) - 1, "num_kv_heads": 1, "additive_mask_shape": None},
    {"query_start_positions": [(1 << 64) - 4, 149], "window_right": 2},
])
def test_prefill_unsigned64_position_size_and_reservation_overflow_rejected(mutation):
    module = helper("prefill-contract")
    plan = module["example"]()
    plan.update(mutation)
    with pytest.raises(ValueError, match="overflow"):
        module["screen"](plan)
    with pytest.raises(ValueError, match="overflow"):
        module["allocation"]((1 << 63) + 1)


def test_decode_baseline_and_legacy_packing_are_predicates_not_observed_dispatch():
    module = helper("decode-contract")
    plan = module["example"]()
    result = module["audit"](plan)
    assert result["layout"] == "hnd" and not result["issues"]
    assert result["specialization_predicate_candidate"] is True
    assert result["declared_cache_payload_bytes"] == 524288
    assert result["native_verification"] == "not_run" and result["physical_fit"] == "not_verified"
    assert "actual dispatch" in result["scope"]
    plan.update(key_shape=[16, 2, 16, 32, 8], value_shape=[16, 2, 128, 32])
    result = module["audit"](plan)
    assert result["layout"] == "legacy-packed" and result["specialization_predicate_candidate"]
    plan["key_shape"] = [16, 2, 32, 32, 4]
    result = module["audit"](plan)
    assert not result["issues"] and not result["specialization_predicate_candidate"]
    assert "block_or_packing" in result["specialization_blockers"]
    plan["sliding_window"] = 128
    assert "sliding_decode_requires_hnd_cache" in module["audit"](plan)["issues"]


def test_decode_fp8_requires_two_declared_scalar_f32_scales_but_no_bytes_are_read():
    module = helper("decode-contract")
    plan = module["example"]()
    plan["cache_dtype"] = "f8e4m3"
    assert "fp8_cache_requires_two_explicit_scalar_f32_scales" in module["audit"](plan)["issues"]
    plan.update(k_scale={"dtype": "f32", "elements": 1},
                v_scale={"dtype": "f32", "elements": 1})
    result = module["audit"](plan)
    assert not result["issues"] and result["declared_cache_payload_bytes"] == 262144
    assert not result["specialization_predicate_candidate"]
    assert set(result["specialization_blockers"]) == {"dtype_pair", "scales"}
    plan["v_scale"]["elements"] = True
    assert "fp8_cache_requires_two_explicit_scalar_f32_scales" in module["audit"](plan)["issues"]
    plan["cache_dtype"] = "bf16"
    assert "non_fp8_cache_must_not_supply_scales" in module["audit"](plan)["issues"]


@pytest.mark.parametrize("mutation,issue", [
    ({"query_shape": [1, 9, 128]},
     "query_cache_head_geometry_mismatch_or_unsupported_head_dimension"),
    ({"value_shape": [16, 2, 32, 64]}, "value_cache_shape_does_not_match_key_layout"),
    ({"context_lens": [513]}, "declared_context_or_table_capacity_mismatch"),
    ({"block_table_shape": [1, 15]}, "declared_context_or_table_capacity_mismatch"),
    ({"context_lens": [1, 2]}, "sequence_metadata_count_mismatch"),
    ({"key_shape": [16, 2, 16, 128], "value_shape": [16, 2, 16, 128]},
     "helper_domain_requires_block32_other_native_specializations_not_screened"),
])
def test_decode_structural_conflicts_are_not_native_rejection_proofs(mutation, issue):
    module = helper("decode-contract")
    plan = module["example"]()
    plan.update(mutation)
    result = module["audit"](plan)
    assert issue in result["issues"]
    assert result["status"] == "declared_contract_conflict"
    assert result["specialization_predicate_candidate"] is False
    assert result["native_verification"] == "not_run"


@pytest.mark.parametrize("mutation,blocker", [
    ({"query_dtype": "f32", "cache_dtype": "f32"}, "dtype_pair"),
    ({"has_alibi": True}, "alibi_or_sinks"), ({"has_sinks": True}, "alibi_or_sinks"),
    ({"softcapping": 2}, "softcapping"), ({"query_shape": [1, 18, 128]}, "gqa_ratio"),
    ({"query_shape": [1, 10, 512], "key_shape": [16, 2, 32, 512],
      "value_shape": [16, 2, 32, 512]}, "specialized_head_domain"),
])
def test_decode_specialization_blockers_remain_distinct_from_valid_metadata(mutation, blocker):
    module = helper("decode-contract")
    plan = module["example"]()
    plan.update(mutation)
    result = module["audit"](plan)
    assert not result["issues"] and blocker in result["specialization_blockers"]
    assert result["specialization_predicate_candidate"] is False


@pytest.mark.parametrize("mutation", [
    {"schema_version": True}, {"unknown": 1}, {"query_shape": [1, 8]},
    {"query_shape": [True, 8, 128]}, {"max_context_len": 1 << 31},
    {"context_lens": []}, {"query_dtype": []}, {"has_sinks": 1},
    {"softcapping": float("nan")}, {"softcapping": float("inf")}, {"softcapping": 0},
    {"softcapping": True}, {"k_scale": {"dtype": "f32"}}, {"v_scale": []},
])
def test_decode_invalid_api_types_and_controls_raise_value_error(mutation):
    module = helper("decode-contract")
    plan = module["example"]()
    plan.update(mutation)
    with pytest.raises(ValueError):
        module["audit"](plan)


def test_decode_large_integer_softcap_is_finite_without_float_conversion():
    module = helper("decode-contract")
    plan = module["example"]()
    plan["softcapping"] = 10 ** 1000
    result = module["audit"](plan)
    assert not result["issues"] and "softcapping" in result["specialization_blockers"]
    assert result["specialization_predicate_candidate"] is False
    assert result["native_verification"] == "not_run"


def test_warmup_inventory_exact_119_source_boundaries_and_small_domain():
    module = helper("qualification")
    result = module["inventory"](module["example"]())
    assert result["batches"] == [1, 2, 4, 5, 8, 9, 32]
    assert result["contexts"] == [
        1, 2, 256, 257, 288, 289, 320, 321, 512, 513, 768, 769,
        1024, 1025, 4096, 4097, 32768,
    ]
    assert result["count"] == 119
    assert result["shapes"] == [
        {"batch": b, "max_context": c} for b in result["batches"] for c in result["contexts"]
    ]
    assert result["status"] == "source_boundary_inventory_only"
    assert result["native_verification"] == "not_run"
    assert result["runtime_eligibility"] == "not_verified"
    plan = {"schema_version": 1, "max_batch": 1, "max_context": 1}
    assert module["inventory"](plan)["shapes"] == [{"batch": 1, "max_context": 1}]
    plan.update(max_batch=3, max_context=257)
    result = module["inventory"](plan)
    assert result["batches"] == [1, 2, 3] and result["contexts"] == [1, 2, 256, 257]
    assert result["count"] == 12


def test_warmup_saturating_uint64_increment_deduplicates_instead_of_wrapping():
    module = helper("qualification")
    maximum = (1 << 64) - 1
    result = module["inventory"]({"schema_version": 1, "max_batch": maximum,
                                  "max_context": maximum})
    assert result["contexts"][-1] == maximum and result["contexts"].count(maximum) == 1
    assert 0 not in result["contexts"] and result["count"] == 119
    assert result["batches"][-1] == maximum


@pytest.mark.parametrize("mutation", [
    {"schema_version": True}, {"schema_version": 2}, {"unknown": 1},
    {"max_batch": 0}, {"max_context": -1}, {"max_batch": True},
    {"max_context": 1.0}, {"max_batch": "32"}, {"max_context": None},
    {"max_context": 1 << 64},
])
def test_warmup_invalid_api_plan_is_not_a_runtime_probe(mutation):
    module = helper("qualification")
    plan = module["example"]()
    plan.update(mutation)
    with pytest.raises(module["PlanError"]):
        module["inventory"](plan)


@pytest.mark.parametrize("area", SCRIPTS)
def test_helper_cli_help_example_and_valid_stdin_file_are_offline(tmp_path, area):
    module = helper(area)
    api = module[{"decode-contract": "audit", "prefill-contract": "screen",
                  "qualification": "inventory"}[area]]
    expected = api(module["example"]())
    result = call_cli(area, "--help", cwd=tmp_path)
    assert result.returncode == 0 and b"usage:" in result.stdout
    result = call_cli(area, "--example", cwd=tmp_path)
    assert result.returncode == 0
    example_output = json.loads(result.stdout)
    assert example_output == (expected if area == "qualification" else module["example"]())
    raw = json.dumps(module["example"]()).encode()
    for args in ((), ("-",)):
        result = call_cli(area, *args, data=raw, cwd=tmp_path)
        assert result.returncode == 0 and json.loads(result.stdout) == expected
    fixture = tmp_path / "plan.json"
    fixture.write_bytes(raw)
    result = call_cli(area, str(fixture), cwd=tmp_path)
    assert result.returncode == 0 and json.loads(result.stdout) == expected
    assert call_cli(area, "--example", str(fixture), cwd=tmp_path).returncode == 2
    result = call_cli(area, str(tmp_path / "private-missing-plan"), cwd=tmp_path)
    assert result.returncode == 2 and not result.stdout
    assert b"private-missing-plan" not in result.stderr and b"Traceback" not in result.stderr
    assert call_cli(area, str(tmp_path), cwd=tmp_path).returncode == 2
    if hasattr(os, "mkfifo"):
        fifo = tmp_path / "input.fifo"
        os.mkfifo(fifo)
        result = call_cli(area, str(fifo), cwd=tmp_path)
        assert result.returncode == 2 and not result.stdout and b"Traceback" not in result.stderr


@pytest.mark.parametrize("area", SCRIPTS)
@pytest.mark.parametrize("raw", [
    b"", b"null", b"[]", b"{}", b"not-json-private-payload", b"\xff",
    b'{"schema_version":1,"schema_version":2}', b'{"schema_version":NaN}',
    b'{"schema_version":Infinity}', b"[" * 1500 + b"0" + b"]" * 1500,
])
def test_all_helper_cli_malformed_input_fails_without_echo_or_traceback(tmp_path, area, raw):
    result = call_cli(area, "-", data=raw, cwd=tmp_path)
    assert result.returncode == 2 and not result.stdout
    assert b"Traceback" not in result.stderr and b"private-payload" not in result.stderr


@pytest.mark.parametrize("area,limit", [
    ("decode-contract", 65536), ("prefill-contract", 1 << 20), ("qualification", 16384),
])
def test_all_helper_cli_size_limits_are_enforced(tmp_path, area, limit):
    result = call_cli(area, "-", data=b" " * (limit + 1), cwd=tmp_path)
    assert result.returncode == 2 and not result.stdout and b"Traceback" not in result.stderr


def test_decode_cli_exit_one_is_declared_conflict_not_native_failure(tmp_path):
    plan = helper("decode-contract")["example"]()
    plan["context_lens"] = [513]
    result = call_cli("decode-contract", "-", data=json.dumps(plan).encode(), cwd=tmp_path)
    assert result.returncode == 1
    value = json.loads(result.stdout)
    assert value["issues"] and value["native_verification"] == "not_run"
    assert value["status"] == "declared_contract_conflict"
