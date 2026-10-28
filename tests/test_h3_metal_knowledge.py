"""Source/declaration delivery checks, never FastH3/Metal/model qualification."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import runpy
import struct
import subprocess
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from inferrsi.catalog import get_knowledge, search_knowledge
from inferrsi.knowledge_operations import KnowledgeReader
from inferrsi.skill_catalog import get_skill, skill_metadata

PROJECT = Path(__file__).resolve().parents[1]
LIBRARY = PROJECT / "src/inferrsi/data/skill_library"
NAME = "audit-h3-metal-fasth3-semantics"
OWNER = LIBRARY / "repositories/h3-metal" / NAME
IDENTITY = "inferrsi.common.skills.audit_h3_metal_fasth3_semantics"
PREFIX = f"data/skill_library/repositories/h3-metal/{NAME}/"
CASES = PROJECT / "tests/fixtures/repo_to_skill/h3-metal/test-cases"
COMMIT = "4ba47a3eabdbebf801ac6664b31f8ec168bc57a8"
SOURCE_MAP_SHA256 = "e53bca079cfc318ae82d35c9cb5e70c61bb2f84a67edcb0af5efffe8b2f407d2"


@pytest.fixture(scope="module")
def helper():
    return runpy.run_path(str(OWNER / "scripts/audit_fasth3.py"))


def test_source_identity_rights_and_candidate_boundaries():
    metadata = skill_metadata(LIBRARY, NAME)
    assert metadata["status"] == "candidate" and metadata["empirical_validation"] == "not_run"
    assert metadata["license"] == "NO_LICENSE"
    primary = metadata["sources"][0]
    source = json.loads((OWNER / primary["identity"]).read_text())
    assert source["commit"] == primary["commit"] == COMMIT
    assert source["repository"] == primary["url"] == "https://github.com/zuiho-kai/h3-metal"
    assert source["native_execution"] == "not_run"
    files = source["files"]
    assert len(files) == len({f["path"] for f in files}) == 21
    assert {f["path"] for f in files} == set(primary["paths"])
    for item in files:
        assert re.fullmatch(r"[0-9a-f]{40}", item["git_blob"])
        assert re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
        assert item["bytes"] > 0 and item["inspected_ranges"]
        assert all(1 <= a <= b for a, b in item["inspected_ranges"])
    hashes = {item["path"]: item["sha256"] for item in files}
    canonical = json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(canonical).hexdigest() == SOURCE_MAP_SHA256
    for path, retained in (
        ("LICENSE", "LICENSE"),
        ("THIRD_PARTY_NOTICES.md", "references/THIRD_PARTY_NOTICES.md"),
    ):
        assert hashlib.sha256((OWNER / retained).read_bytes()).hexdigest() == hashes[path]
    assert "Salvatore Sanfilippo" in (OWNER / "LICENSE").read_text()
    assert "Liu Liu" in (OWNER / "references/THIRD_PARTY_NOTICES.md").read_text()
    assert "BLOCKED_REQUIRED_BACKEND" in " ".join(metadata["limitations"])


def test_discovery_and_complete_checkout_package_resources():
    record = get_knowledge(IDENTITY)
    for query in ("h3-metal", "FastH3", "VSA fallback"):
        assert record in search_knowledge(query, repo="inferrsi", limit=100)
    assert record["status"] == "imported" and record["skill_metadata"]["status"] == "candidate"
    assert record["verification"]["locally_verified"] is False
    reader = KnowledgeReader(skill_root=LIBRARY)
    local, packaged = reader.read(NAME), reader.read(IDENTITY)
    for relative in set(get_skill(LIBRARY, NAME)["resources"]) | {"SKILL.md"}:
        expected = (OWNER / relative).read_bytes()
        assert packaged.content[PREFIX + relative] == expected
        assert local.content[f"repositories/h3-metal/{NAME}/{relative}"] == expected
        assert reader.resource(IDENTITY, PREFIX + relative, revision=packaged.revision) == expected


def test_runtime_links_are_contained_and_no_review_or_environment_debris():
    for path in OWNER.rglob("*.md"):
        content = path.read_text()
        assert "/workspace/" not in content and "/home/agent/" not in content
        for target in re.findall(r"\]\(([^)]+)\)", content):
            link = urlsplit(target)
            if link.scheme or not link.path:
                continue
            resolved = (path.parent / unquote(link.path)).resolve()
            assert resolved.is_relative_to(OWNER.resolve()) and resolved.is_file(), (path, target)
    assert not any(
        p.name in {"evals", "reports", "test-cases", "__pycache__"} for p in OWNER.rglob("*")
    )


def test_effective_configuration_is_not_requested_flags_or_backend_proof(helper):
    result = helper["audit"](helper["example"]())
    assert result["effective_parameters"] == helper["PARAMETERS"]
    assert len(result["parameter_overrides"]) == 6
    assert result["temporal"] == {
        "requested_frames": 49,
        "aligned_frames": 56,
        "video_latent_t": 17,
    }
    assert result["layout"]["video_tiles"] == 120
    assert result["layout"]["topk_double"] == 12
    assert result["attention_path"] == "dense_fine_plus_gated_coarse"
    assert result["reuse_steps_effect"] == "ignored_by_normalized_reuse_1"
    assert all(result[k] == "not_run" for k in ("native_execution", "quality", "performance"))


@pytest.mark.parametrize("value", ["", "0", "1", "false"])
def test_sparse_disable_checks_presence_not_truth(helper, value):
    data = helper["example"]()
    data["environment"] = {"H3_DISABLE_FASTH3_SPARSE": value}
    data["sparse_pipeline_available"] = True
    assert helper["audit"](data)["attention_path"] == "dense_fine_plus_gated_coarse"


@pytest.mark.parametrize(
    "pipeline,path",
    [
        (None, "unknown_sparse_pipeline_availability"),
        (False, "dense_fine_plus_gated_coarse"),
        (True, "sparse_fine_plus_gated_coarse_if_native_constraints_hold"),
    ],
)
def test_pipeline_unknown_is_not_promoted(helper, pipeline, path):
    data = {"fasth3": True, "sparse_pipeline_available": pipeline}
    assert helper["audit"](data)["attention_path"] == path


def test_ambient_reduction_and_ordered_refs_are_findings_not_silent_normalization(helper):
    data = {
        "fasth3": True,
        "reference_count": 1,
        "environment": {"H3_TOKEN_REDUCTION": "1", "H3_DISABLE_TOKEN_REDUCTION": "0"},
    }
    result = helper["audit"](data)
    assert result["effective_parameters"]["token_reduction"] == 0
    assert result["issues"] == [
        "ordered_ref2va_references_rejected",
        "ambient_token_reduction_conflicts_with_fasth3",
        "reduction_forward_disabled_by_key_presence_but_configuration_still_enabled",
    ]


def test_real_partial_tile_counts_and_adjacent_prefix_merge_against_coordinate_oracle(helper):
    latent = {"t": 5, "h": 10, "w": 10}
    result = helper["layout"](
        latent,
        [
            {"kind": "text", "rows": 6},
            {"kind": "cond", "rows": 32},
            {"kind": "cond", "rows": 32},
            {"kind": "audio", "rows": 65},
        ],
    )
    # Independent coordinate enumeration catches an all-64/padded edge implementation.
    counts = Counter((t // 4, h // 4, w // 4) for t in range(5) for h in range(5) for w in range(5))
    histogram = {str(k): v for k, v in Counter(counts.values()).items()}
    assert result["video_tile_row_histogram"] == histogram == {"64": 1, "16": 3, "4": 3, "1": 1}
    assert result["video_tile_rows_sum"] == result["video_rows"] == 125
    assert result["prefix_tile_counts"] == [6, 64, 64, 1]
    assert result["video_query_key_tiles"] == 5  # all four prefix tiles + one video tile
    assert result["prefix_query_key_tiles"] == 12


def test_double_ceil_counterexample_and_label_mapping_not_shape_equivalence(helper):
    f32 = lambda x: struct.unpack("f", struct.pack("f", x))[0]  # noqa: E731
    assert math.ceil(f32(f32(1.0 - f32(0.9)) * 120)) == 13
    assert math.ceil((1.0 - 0.9) * 120) == 12
    probes = helper["mapping_probes"]()
    assert probes["qkv_head_interleaved"] == [
        "q0",
        "q1",
        "k0",
        "k1",
        "v0",
        "v1",
        "q2",
        "q3",
        "k2",
        "k3",
        "v2",
        "v3",
    ]
    assert Counter(probes["qkv_head_interleaved"]) == Counter(probes["qkv_wrong_global_concat"])
    assert probes["qkv_head_interleaved"] != probes["qkv_wrong_global_concat"]
    assert probes["fc1_swapped"] == ["c", "d", "a", "b"] != probes["fc1_source"]


def test_original_h3_regression_preserves_requested_parameters_and_declines_dispatch(helper):
    data = helper["example"]()
    data["fasth3"] = False
    result = helper["audit"](data)
    assert result["effective_parameters"] == data["requested"]
    assert result["parameter_overrides"] == {}
    assert result["attention_path"] == "not_audited_original_h3"
    assert result["mapping_probes"] is None


@pytest.mark.parametrize(
    "patch",
    [
        {},
        {"fasth3": 1},
        {"fasth3": True, "unknown": 1},
        {"fasth3": True, "requested": {"steps": True}},
        {"fasth3": True, "requested": {"steps": -1}},
        {"fasth3": True, "environment": {"SECRET": "not-read"}},
        {"fasth3": True, "environment": {"H3_TOKEN_REDUCTION": None}},
        {"fasth3": True, "sparse_pipeline_available": 1},
        {"fasth3": True, "reference_count": True},
        {"fasth3": True, "latent_shape": {"t": 5, "h": 10, "w": 10}},
        {"fasth3": True, "latent_shape": {"t": 5, "h": 9, "w": 10}, "prefix_segments": []},
        {"fasth3": True, "latent_shape": {"t": 512, "h": 512, "w": 512}, "prefix_segments": []},
        {
            "fasth3": True,
            "latent_shape": {"t": 5, "h": 10, "w": 10},
            "prefix_segments": [{"kind": "ref_image", "rows": 1}],
        },
    ],
)
def test_invalid_selected_input_fails_without_native_fallback(helper, patch):
    with pytest.raises(ValueError):
        helper["audit"](copy.deepcopy(patch))


def test_cli_runs_outside_checkout_ignores_ambient_state_and_writes_no_files(tmp_path, helper):
    script = OWNER / "scripts/audit_fasth3.py"
    env = {**os.environ, "H3_TOKEN_REDUCTION": "1", "H3_DISABLE_FASTH3_SPARSE": "1"}
    data = {"fasth3": True, "sparse_pipeline_available": True}
    result = subprocess.run(
        [sys.executable, "-I", str(script)],
        input=json.dumps(data),
        text=True,
        capture_output=True,
        cwd=tmp_path,
        env=env,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == helper["audit"](data)
    assert not list(tmp_path.iterdir())
    for raw in ('{"fasth3":true,"fasth3":false}', "{", " " * 65537):
        bad = subprocess.run(
            [sys.executable, "-I", str(script)],
            input=raw,
            text=True,
            capture_output=True,
            cwd=tmp_path,
            timeout=10,
        )
        assert bad.returncode == 2 and not bad.stdout
        assert json.loads(bad.stderr)["native_execution"] == "not_run"


def test_assertion_cases_are_external_complete_and_have_valid_runtime_targets():
    requests = list(CASES.rglob("user_request.txt"))
    assert len(requests) == 4
    for request in requests:
        assert not request.read_text().startswith("#")
        case = request.parent
        assert (case / "README.md").is_file()
        assertions = json.loads((case / "assertions.json").read_text())
        assert assertions["schema"] == "disco.usability-case.v1"
        assert len(assertions["assertions"]) >= 5
        for relative in assertions["expected_skill_files"]:
            assert (OWNER / relative).is_file()


@pytest.mark.parametrize(
    "arguments,raw,code",
    [
        ([], "[" * 10000 + "0" + "]" * 10000, "invalid_input"),
        ([], '{"private-test-marker":0,"private-test-marker":1}', "invalid_input"),
        (["--private-test-marker"], "", "invalid_arguments"),
        (["--example", "private-test-marker"], "", "invalid_arguments"),
    ],
)
def test_cli_invalid_input_diagnostics_are_bounded_and_non_echoing(
    tmp_path,
    arguments,
    raw,
    code,
):
    script = OWNER / "scripts/audit_fasth3.py"
    result = subprocess.run(
        [sys.executable, "-I", str(script), *arguments],
        input=raw,
        text=True,
        capture_output=True,
        cwd=tmp_path,
        timeout=10,
    )
    assert result.returncode == 2 and result.stdout == ""
    assert json.loads(result.stderr) == {"error": code, "native_execution": "not_run"}
    assert len(result.stderr) < 100
    assert "private-test-marker" not in result.stderr
    assert "Traceback" not in result.stderr and str(PROJECT) not in result.stderr
    assert not list(tmp_path.iterdir())
