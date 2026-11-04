"""Candidate graph and declaration helpers; not Swift/MLX/Metal qualification."""

from __future__ import annotations

import copy
import hashlib
import itertools
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
ROOT = PROJECT / "src/inferrsi/data/skill_library/repositories/mlx-swift-lm"
CASES = PROJECT / "tests/fixtures/repo_to_skill/mlx-swift-lm/test-cases"
SOURCE_COMMIT = "3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac"
SOURCE_FILES_SHA256 = "df10bf7c0523c89c51e37f61eb79323b256879538874b33c03a2e242e3762705"
MIT_SHA256 = "7b1d86acac816ce8192209d7e01141c129b4d48d474c15cc5fb4af62f497c323"
SCRIPTS = {
    "gated-delta-contract": "audit_gated_delta_declarations.py",
    "generation-lifecycle": "audit_generation_evidence.py",
}


def helper(area):
    return runpy.run_path(str(ROOT / "sub-skills" / area / "scripts" / SCRIPTS[area]))


def call_cli(area, *args, data=None, cwd=None):
    script = ROOT / "sub-skills" / area / "scripts" / SCRIPTS[area]
    return subprocess.run(
        [sys.executable, str(script), *args], input=data, capture_output=True,
        timeout=10, cwd=cwd, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


@pytest.fixture(scope="module")
def gdn():
    return helper("gated-delta-contract")


@pytest.fixture(scope="module")
def lifecycle():
    return helper("generation-lifecycle")


def test_mlx_swift_graph_is_contained_candidate_with_exact_34_file_scope():
    paths = list(ROOT.rglob("SKILL.md"))
    assert len(paths) == 3
    for path in paths:
        header = path.read_text().split("---", 2)[1]
        value = yaml.safe_load(header)
        assert value["name"] == path.parent.name
        assert value["license"] == "NO_LICENSE"
        assert value["disable-model-invocation"] is True
        assert value["metadata"]["disco-role"] == "operating"
        assert len(re.findall(r'^description: ".+"$', header, re.MULTILINE)) == 1
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
    assert metadata["schema_version"] == 1 and metadata["kind"] == "skill"
    assert metadata["status"] == "candidate" and metadata["empirical_validation"] == "not_run"
    assert metadata["construction"]["native_import"] == "not-run"
    assert "BLOCKED_REQUIRED_BACKEND" in " ".join(metadata["limitations"])
    source = json.loads((ROOT / "references/source-identity.json").read_text())
    assert source["schema_version"] == 1 and source["repository"] == "ml-explore/mlx-swift-lm"
    assert source["source_commit"] == metadata["sources"][0]["commit"] == SOURCE_COMMIT
    assert len(source["files"]) == 34
    assert set(source["files"]) == set(source["inspected_sections"])
    assert set(source["files"]) == set(metadata["sources"][0]["paths"])
    assert all(re.fullmatch(r"[a-f0-9]{64}", value) for value in source["files"].values())
    assert all(isinstance(span, str) and span for span in source["inspected_sections"].values())
    # Freeze the exact selected path/hash map without requiring an upstream checkout in CI.
    canonical = json.dumps(source["files"], sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(canonical).hexdigest() == SOURCE_FILES_SHA256
    source_skill_scope = source["inspected_sections"]["skills/mlx-swift-lm/SKILL.md"]
    assert "449" in source_skill_scope and "truncated" not in source_skill_scope.lower()
    assert source["files"]["LICENSE"] == MIT_SHA256
    assert hashlib.sha256((ROOT / "LICENSE").read_bytes()).hexdigest() == MIT_SHA256
    assert not list(ROOT.rglob("__pycache__"))
    assert not list(ROOT.rglob("assertions.json"))


def test_mlx_swift_cases_cover_both_routes_root_and_integrated_limits():
    paths = list(CASES.rglob("assertions.json"))
    assert len(paths) == 8
    assert len(list((CASES / "root").glob("*/assertions.json"))) == 2
    assert len(list((CASES / "integration").glob("*/assertions.json"))) == 2
    for area in SCRIPTS:
        assert len(list((CASES / "sub-skills" / area).glob("*/assertions.json"))) == 2
    source = json.loads((ROOT / "references/source-identity.json").read_text())
    for path in paths:
        value = json.loads(path.read_text())
        assert value["schema"] == "disco.usability-case.v1"
        assert value["assertions"] and value["evidence_basis"]
        assert set(value["evidence_basis"]) <= set(source["files"])
        assert (path.parent / "user_request.txt").read_text().strip()
        assert (path.parent / "README.md").read_text().strip()
        for relative in value["expected_skill_files"]:
            resolved = (ROOT / relative).resolve()
            assert resolved.is_relative_to(ROOT.resolve()) and resolved.is_file()


def test_gdn_base_is_one_fp32_payload_and_unknown_gate_not_native_fit(gdn):
    result = gdn["audit"](gdn["example"]())
    assert result["status"] == "declarations_screened_only"
    assert result["literal_public_gate"] == "undetermined"
    assert result["declared_branch"] == "unmasked_availability_not_established"
    assert result["expected_output_shape"] == [1, 40, 4, 16]
    assert result["expected_carried_state_shape"] == [1, 4, 16, 32]
    assert result["effective_carried_state_dtype"] == "float32"
    assert result["one_carried_state_payload_bytes"] == 8192
    assert result["one_output_payload_bytes"] == 5120
    for excluded in (
        "convolution", "checkpoint", "offset/padding/length", "other caches", "pressure",
    ):
        assert excluded in result["state_payload_scope"]
    assert result["native_verification"] == result["compiler_check"] == "not_run"
    for field in (
        "actual_dispatch", "numerical_correctness", "stride_provider_contract", "physical_fit",
    ):
        assert result[field] == "not_verified"


@pytest.mark.parametrize("use_kernel,key_dim,unmasked,masked,masked_availability,training", list(
    itertools.product(
        [False, True], [32, 48], ["available", "unavailable", "unknown"],
        [False, True], ["available", "unavailable", "unknown"], [False, True],
    )
))
def test_gdn_literal_predicate_domain_never_proves_actual_route(
    gdn, use_kernel, key_dim, unmasked, masked, masked_availability, training,
):
    plan = gdn["example"]()
    plan.update(use_kernel=use_kernel, unmasked_kernel_availability=unmasked,
                masked_kernel_availability=masked_availability, training=training)
    plan["q_shape"][3] = plan["k_shape"][3] = key_dim
    plan["mask_shape"] = [1, 40] if masked else None
    result = gdn["audit"](plan)
    expected = (
        "false" if not use_kernel or key_dim % 32 or unmasked == "unavailable"
        else "undetermined" if unmasked == "unknown" else "true"
    )
    assert result["literal_public_gate"] == expected
    assert result["key_dimension_tail_mod32"] == key_dim % 32
    assert result["one_carried_state_payload_bytes"] == 1 * 4 * 16 * key_dim * 4
    assert (result["training_caller_warning"] is not None) == (training and use_kernel)
    if expected == "false":
        assert result["declared_branch"] == "ops_fallback_by_declared_public_gate"
    elif expected == "true" and masked and masked_availability == "unavailable":
        assert result["declared_branch"] == (
            "selected_masked_kernel_nil_fatal_branch_by_declarations"
        )
    elif expected == "true" and masked and masked_availability == "unknown":
        assert result["declared_branch"] == "masked_kernel_availability_not_established"
    if masked:
        assert result["masked_output_parity"] == "source_asymmetry_unexecuted"
    assert result["actual_dispatch"] == "not_verified"
    assert result["native_verification"] == "not_run"
    assert "cpu" not in json.dumps(result).lower()  # Ops selection is not a CPU result.


@pytest.mark.parametrize("dtype,conversion", [
    ("float32", "retained_float32"), ("bfloat16", "cast_to_float32"),
    ("float16", "cast_to_float32"),
])
def test_gdn_explicit_state_and_token_length_do_not_change_precision_contract(
    gdn, dtype, conversion,
):
    plan = gdn["example"]()
    plan["state"] = {"shape": [1, 4, 16, 32], "dtype": dtype}
    result = gdn["audit"](plan)
    assert result["state_conversion"] == conversion
    assert result["one_carried_state_payload_bytes"] == 8192
    for field in ("q_shape", "k_shape", "v_shape", "a_shape", "b_shape"):
        plan[field][1] = 80
    result = gdn["audit"](plan)
    assert result["one_carried_state_payload_bytes"] == 8192
    assert result["one_output_payload_bytes"] == 10240


def test_gdn_tail48_and_low_precision_state_require_ops_without_recovered_precision_claim(gdn):
    plan = gdn["example"]()
    plan["q_shape"][3] = plan["k_shape"][3] = 48
    plan.update(state={"shape": [1, 4, 16, 48], "dtype": "bfloat16"},
                unmasked_kernel_availability="available", training=True)
    result = gdn["audit"](plan)
    assert result["literal_public_gate"] == "false"
    assert "key_dimension_has_simd_tail" in result["gate_false_reasons"]
    assert result["key_dimension_tail_mod32"] == 16
    assert result["state_conversion"] == "cast_to_float32"
    assert result["one_carried_state_payload_bytes"] == 12288
    assert result["training_caller_warning"] and result["numerical_correctness"] == "not_verified"


@pytest.mark.parametrize("mutation", [
    {"schema_version": True}, {"extra": 1}, {"input_dtype": []}, {"input_dtype": "int8"},
    {"use_kernel": 1}, {"training": None}, {"unmasked_kernel_availability": {}},
    {"masked_kernel_availability": float("nan")}, {"q_shape": [True, 40, 2, 32]},
    {"q_shape": [1, 40, 2]}, {"k_shape": [1, 40, 2, 48]}, {"v_shape": [1, 40, 3, 16]},
    {"a_shape": [1, 40, 3]}, {"b_shape": [1, 0, 4]}, {"a_log_shape": [True]},
    {"dt_bias_shape": [3]}, {"mask_shape": [1, 40, 4]}, {"mask_shape": [2, 40]},
    {"state": []}, {"state": {"shape": [1, 4, 16, 32], "dtype": []}},
    {"state": {"shape": [1, 4, 16, 31], "dtype": "float32"}},
    {"state": {"shape": [1, 4, 16, 32], "dtype": "float32", "extra": 1}},
])
def test_gdn_malformed_schema_shapes_and_descriptors_raise_value_error(gdn, mutation):
    plan = gdn["example"]()
    plan.update(copy.deepcopy(mutation))
    with pytest.raises(ValueError):
        gdn["audit"](plan)


def test_gdn_payload_overflow_is_not_an_allocation_attempt(gdn):
    plan = gdn["example"]()
    for field in ("q_shape", "k_shape", "v_shape", "a_shape", "b_shape"):
        plan[field][1] = (1 << 63) - 1
    with pytest.raises(ValueError, match="payload arithmetic"):
        gdn["audit"](plan)


def test_lifecycle_example_preserves_info_join_and_identity_gaps(lifecycle):
    result = lifecycle["audit"](lifecycle["example"]())
    assert result["status"] == "caller_evidence_records_audited_only"
    assert result["summary"] == {
        "records": 2, "join_declared_completed": 1, "cleanup_unresolved": 1,
        "records_with_conflicts": 0, "records_with_uncertainty": 2, "final_info_observed": 2,
    }
    assert set(result["identity_gaps"]) == {
        "resolved_mlx_revision_not_recorded", "native_backend_not_recorded_or_not_run",
    }
    assert result["records"][0]["declared_final_info"]["stop_reason"] == "cancelled"
    assert result["records"][0]["cleanup_evidence"] == "unresolved"
    assert result["records"][1]["cleanup_evidence"] == "caller_declared_join_only"
    assert result["engine_execution"] == "not_run_by_helper"
    assert result["native_verification"] == "not_run"
    assert result["evidence_authentication"] == "not_verified"


@pytest.mark.parametrize("stop_reason", ["stop", "length", "cancelled"])
def test_lifecycle_completed_join_remains_declared_and_does_not_infer_stop_reason(
    lifecycle, stop_reason,
):
    plan = lifecycle["example"]()
    plan.update(resolved_mlx_commit="a" * 40, declared_backend="metal")
    record = plan["records"][0]
    record.update(consumer_end="early_break", producer_task_join="completed",
                  mlx_default_stream_sync="observed",
                  final_info={"stop_reason": stop_reason, "generation_token_count": 0})
    plan["records"] = [record]
    result = lifecycle["audit"](plan)
    row = result["records"][0]
    assert not result["identity_gaps"] and not row["conflicts"] and not row["uncertainty"]
    assert row["cleanup_evidence"] == "caller_declared_join_only"
    assert row["declared_final_info"]["stop_reason"] == stop_reason
    assert result["evidence_authentication"] == "not_verified"
    record["final_info"] = None
    result = lifecycle["audit"](plan)
    assert result["records"][0]["cleanup_evidence"] == "caller_declared_join_only"
    assert "final_info_not_observed_not_a_failure_verdict" in result["records"][0]["uncertainty"]
    assert result["summary"]["final_info_observed"] == 0 and "verdict" not in result


@pytest.mark.parametrize("api", ["generate", "ModelContainer.generate"])
def test_lifecycle_stream_api_cannot_supply_a_producer_task_join(lifecycle, api):
    plan = lifecycle["example"]()
    plan["records"] = [plan["records"][1]]
    plan["records"][0]["api"] = api
    result = lifecycle["audit"](plan)
    row = result["records"][0]
    assert row["join_declared_completed"] is True and row["cleanup_evidence"] == "unresolved"
    assert set(row["conflicts"]) == {
        "api_does_not_expose_producer_task_handle", "stream_only_api_does_not_expose_producer_join",
    }
    assert result["summary"]["records_with_conflicts"] == 1


@pytest.mark.parametrize("retained", [False, None])
def test_lifecycle_completed_join_without_matching_retained_handle_is_conflict(lifecycle, retained):
    plan = lifecycle["example"]()
    plan["records"][1]["producer_task_retained"] = retained
    result = lifecycle["audit"](plan)
    row = result["records"][1]
    assert row["conflicts"] == ["completed_join_without_retained_producer_handle"]
    assert row["cleanup_evidence"] == "unresolved"


def test_lifecycle_out_of_contract_identity_and_unobserved_end_remain_gaps(lifecycle):
    plan = lifecycle["example"]()
    plan["source_commit"] = "b" * 40
    plan["records"][0]["consumer_end"] = "not_observed"
    result = lifecycle["audit"](plan)
    assert "source_revision_outside_reviewed_contract" in result["identity_gaps"]
    assert "consumer_end_not_observed" in result["records"][0]["uncertainty"]
    assert result["native_verification"] == "not_run"


@pytest.mark.parametrize("mutation", [
    {"schema_version": True}, {"unknown": 1}, {"source_repository": []},
    {"source_commit": "A" * 40}, {"source_commit": "a" * 39},
    {"resolved_mlx_commit": []}, {"declared_backend": {}}, {"records": []},
])
def test_lifecycle_invalid_identity_and_top_level_fields_raise(lifecycle, mutation):
    plan = lifecycle["example"]()
    plan.update(copy.deepcopy(mutation))
    with pytest.raises(ValueError):
        lifecycle["audit"](plan)


@pytest.mark.parametrize("mutation", [
    {"generation_id": []}, {"generation_id": "private/path"}, {"api": []},
    {"consumer_end": None}, {"producer_task_retained": 1}, {"producer_task_join": []},
    {"mlx_default_stream_sync": True}, {"extra": 1}, {"final_info": []},
    {"final_info": {"stop_reason": "stop", "generation_token_count": True}},
    {"final_info": {"stop_reason": "stop", "generation_token_count": -1}},
    {"final_info": {"stop_reason": "stop", "generation_token_count": 1 << 63}},
    {"final_info": {"stop_reason": "stop", "generation_token_count": float("inf")}},
    {"final_info": {"stop_reason": [], "generation_token_count": 1}},
    {"final_info": {"stop_reason": "stop", "generation_token_count": 1, "extra": 0}},
])
def test_lifecycle_bad_record_and_final_info_descriptors_raise(lifecycle, mutation):
    plan = lifecycle["example"]()
    plan["records"][0].update(copy.deepcopy(mutation))
    with pytest.raises(ValueError):
        lifecycle["audit"](plan)


def test_lifecycle_duplicate_ids_and_unbounded_record_count_raise(lifecycle):
    plan = lifecycle["example"]()
    plan["records"][1]["generation_id"] = plan["records"][0]["generation_id"]
    with pytest.raises(ValueError, match="unique"):
        lifecycle["audit"](plan)
    plan["records"] = [copy.deepcopy(plan["records"][0]) for _ in range(129)]
    with pytest.raises(ValueError, match="bounded list"):
        lifecycle["audit"](plan)


@pytest.mark.parametrize("area", SCRIPTS)
def test_mlx_swift_helpers_cli_help_examples_stdin_and_regular_file_are_offline(tmp_path, area):
    module = helper(area)
    expected = module["audit"](module["example"]())
    result = call_cli(area, "--help", cwd=tmp_path)
    assert result.returncode == 0 and b"usage:" in result.stdout
    result = call_cli(area, "--example", cwd=tmp_path)
    assert result.returncode == 0 and json.loads(result.stdout) == module["example"]()
    raw = json.dumps(module["example"]()).encode()
    for args in ((), ("-",)):
        result = call_cli(area, *args, data=raw, cwd=tmp_path)
        assert result.returncode == 0 and json.loads(result.stdout) == expected
    fixture = tmp_path / "declarations.json"
    fixture.write_bytes(raw)
    result = call_cli(area, str(fixture), cwd=tmp_path)
    assert result.returncode == 0 and json.loads(result.stdout) == expected


@pytest.mark.parametrize("area", SCRIPTS)
@pytest.mark.parametrize("raw", [
    b"", b"null", b"[]", b"{}", b"not-json-private-payload", b"\xff",
    b'{"schema_version":1,"schema_version":2}', b'{"schema_version":NaN}',
    b'{"schema_version":Infinity}', b"[" * 1500 + b"0" + b"]" * 1500,
    b" " * 65537,
])
def test_mlx_swift_helpers_cli_bad_json_is_bounded_without_echo_or_traceback(tmp_path, area, raw):
    result = call_cli(area, "-", data=raw, cwd=tmp_path)
    assert result.returncode == 2 and not result.stdout
    assert b"Traceback" not in result.stderr and b"private-payload" not in result.stderr


@pytest.mark.parametrize("area", SCRIPTS)
def test_mlx_swift_helpers_cli_private_paths_bad_args_and_fifo_are_not_echoed(tmp_path, area):
    private = tmp_path / "private-synthetic-marker"
    for args in ((str(private),), (str(tmp_path),), ("--example", str(private)),
                 (str(private), str(private)), ("--unknown=private-synthetic-marker",)):
        result = call_cli(area, *args, cwd=tmp_path)
        assert result.returncode == 2 and not result.stdout
        assert b"Traceback" not in result.stderr
        assert b"private-synthetic-marker" not in result.stderr
        assert str(tmp_path).encode() not in result.stderr
    if hasattr(os, "mkfifo"):
        fifo = tmp_path / "private-synthetic-marker.fifo"
        os.mkfifo(fifo)
        result = call_cli(area, str(fifo), cwd=tmp_path)
        assert result.returncode == 2 and not result.stdout and b"Traceback" not in result.stderr
        assert b"private-synthetic-marker" not in result.stderr


def test_gdn_cli_declared_fatal_branch_still_is_not_executed_native_failure(tmp_path, gdn):
    plan = gdn["example"]()
    plan.update(mask_shape=[1, 40], unmasked_kernel_availability="available",
                masked_kernel_availability="unavailable")
    result = call_cli("gated-delta-contract", "-", data=json.dumps(plan).encode(), cwd=tmp_path)
    assert result.returncode == 0
    value = json.loads(result.stdout)
    assert value["literal_public_gate"] == "true"
    assert value["declared_branch"] == "selected_masked_kernel_nil_fatal_branch_by_declarations"
    assert value["masked_output_parity"] == "source_asymmetry_unexecuted"
    assert value["actual_dispatch"] == "not_verified" and value["native_verification"] == "not_run"
