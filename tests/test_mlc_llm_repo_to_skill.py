"""MLC artifact, target and limit declaration contracts and packaged resources."""

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
ROOT = PROJECT / "src/inferrsi/data/skill_library/repositories/mlc-llm"
CASES = PROJECT / "tests/fixtures/repo_to_skill/mlc-llm/test-cases"
SCRIPTS = {
    "artifact-contract": "audit_artifact_declarations.py",
    "metal-build-runtime": "audit_apple_target_declarations.py",
    "runtime-kv-limits": "audit_kv_limit_declarations.py",
}


@pytest.fixture(scope="module")
def modules():
    return {area: runpy.run_path(str(ROOT / "sub-skills" / area / "scripts" / filename))
            for area, filename in SCRIPTS.items()}


def test_mlc_graph_source_owners_rights_and_containment():
    for path in ROOT.rglob("SKILL.md"):
        header = path.read_text().split("---", 2)[1]
        value = yaml.safe_load(header)
        assert value["name"] == path.parent.name
        assert value["license"] == "NO_LICENSE"
        assert value["disable-model-invocation"] is True
        assert value["metadata"]["disco-role"] == "operating"
        assert re.search(r'^description: ".+"$', header, re.MULTILINE)
    assert len(list(ROOT.rglob("SKILL.md"))) == 4
    for path in ROOT.rglob("*.md"):
        content = path.read_text()
        assert "/workspace/" not in content and "/home/agent/" not in content
        for target in re.findall(r"\]\(([^)]+)\)", content):
            link = urlsplit(target)
            if link.scheme or not link.path:
                continue
            resolved = (path.parent / unquote(link.path)).resolve()
            assert resolved.is_relative_to(ROOT.resolve()) and resolved.is_file(), (path, target)
    meta = json.loads((ROOT / "metadata.json").read_text())
    assert meta["status"] == "candidate" and meta["empirical_validation"] == "not_run"
    assert "BLOCKED_REQUIRED_BACKEND" in " ".join(meta["limitations"])
    identity = json.loads((ROOT / "references/source-identity.json").read_text())
    sources = {source["repository"]: source for source in identity["sources"]}
    assert set(sources) == {"mlc-ai/mlc-llm", "mlc-ai/relax"}
    assert [len(sources[repo]["files"]) for repo in ("mlc-ai/mlc-llm", "mlc-ai/relax")] == [29, 10]
    for source in sources.values():
        assert set(source["files"]) == set(source["inspected_sections"])
        assert all(re.fullmatch(r"[a-f0-9]{64}", value) for value in source["files"].values())
    assert identity["gitlinks"][0]["commit"] == sources["mlc-ai/relax"]["commit"]
    assert identity["gitlinks"][0]["url"] == "https://github.com/mlc-ai/relax.git"
    for repo, upstream, local in (
        ("mlc-ai/mlc-llm", "LICENSE", "LICENSE"),
        ("mlc-ai/mlc-llm", "NOTICE", "references/mlc-notice.md"),
        ("mlc-ai/relax", "LICENSE", "references/tvm-license.md"),
        ("mlc-ai/relax", "NOTICE", "references/tvm-notice.md"),
    ):
        assert hashlib.sha256((ROOT / local).read_bytes()).hexdigest() == (
            sources[repo]["files"][upstream]
        )
    assert not list(ROOT.rglob("__pycache__"))


def test_mlc_case_resources_and_source_paths_are_exact():
    paths = list(CASES.rglob("assertions.json"))
    assert len(paths) == 10
    assert len(list((CASES / "root").glob("*/assertions.json"))) == 2
    assert len(list((CASES / "integration").glob("*/assertions.json"))) == 2
    sources = json.loads((ROOT / "references/source-identity.json").read_text())["sources"]
    source_paths = {source["repository"] + ":" + path
                    for source in sources for path in source["files"]}
    for area in SCRIPTS:
        assert len(list((CASES / "sub-skills" / area).glob("*/assertions.json"))) == 2
    for path in paths:
        value = json.loads(path.read_text())
        assert value["schema"] == "disco.usability-case.v1" and value["assertions"]
        assert set(value["evidence_basis"]) <= source_paths
        assert (path.parent / "user_request.txt").read_text().strip()
        for target in value["expected_skill_files"]:
            resolved = (ROOT / target).resolve()
            assert resolved.is_relative_to(ROOT.resolve()) and resolved.is_file()


def test_artifact_canonical_ids_and_parameter_only_bytes(modules):
    module = modules["artifact-contract"]
    plan = module["example"]()
    result = module["audit"](plan)
    canonical = json.dumps({"tasks": plan["tasks"]}, ensure_ascii=False,
                           separators=(",", ":"), sort_keys=True).encode()
    assert result["interface_id"] == "sha256:" + hashlib.sha256(canonical).hexdigest()
    assert result["metadata_consistent"] and not result["findings"]
    assert result["resources"]["max_storage_buffer_binding_size"] == 20
    assert result["resources"]["estimated_device_memory_bytes"] == 32
    assert result["weight_bytes"] == "not_read"
    assert result["exports_and_abi"] == "not_verified"
    assert result["native_execution"] == result["compiler_check"] == "not_run"
    plan["parameters"].reverse()
    assert module["audit"](plan)["parameter_schema_id"] == result["parameter_schema_id"]
    plan["programs"]["generation"]["exports"]["decode_embeds"] = "another_symbol"
    assert module["audit"](plan)["interface_id"] == result["interface_id"]


def test_artifact_symbols_resources_and_role_conflicts(modules):
    module = modules["artifact-contract"]
    plan = module["example"]()
    plan["parameters"] = [{"name": "embed", "shape": ["vocab_size", 4], "dtype": "float16"},
                          {"name": "bias", "shape": [6], "dtype": "float32"}]
    plan["symbolic_sizes"] = {"vocab_size": 10}
    first = module["audit"](plan)
    plan["symbolic_sizes"]["vocab_size"] = 20
    second = module["audit"](plan)
    assert first["parameter_schema_id"] == second["parameter_schema_id"]
    assert [r["resources"]["estimated_device_memory_bytes"] for r in (first, second)] == [104, 184]
    assert [r["resources"]["max_storage_buffer_binding_size"] for r in (first, second)] == [80, 160]
    plan["programs"]["generation"]["exports"]["prefill_tokens"] = "prefill_ids"
    result = module["audit"](plan)
    assert not result["metadata_consistent"]
    assert "token_generation_incomplete_role_pair" in result["findings"]
    plan["symbolic_sizes"] = {}
    with pytest.raises(ValueError):
        module["audit"](plan)


@pytest.mark.parametrize("mutation", [
    {"schema_version": True}, {"required_features": [False]}, {"declared_ids": {}},
    {"parameters": [{"name": "p", "shape": [True], "dtype": "float16"}]},
    {"parameters": [{"name": "p", "shape": [1], "dtype": "int8"}]},
])
def test_artifact_strict_declaration_domain(modules, mutation):
    module = modules["artifact-contract"]
    plan = module["example"]()
    plan.update(copy.deepcopy(mutation))
    with pytest.raises(ValueError):
        module["audit"](plan)


@pytest.mark.parametrize("hint,suffix,prefix,arch", list(itertools.product(
    ["iphone", "iphone:generic", "macabi", "macabi:generic", "metal:x86-64", "metal:generic"],
    [".tar", ".dylib", ".bin"], ["auto", "", "custom_prefix"], [None, "x86_64", "bad"],
)))
def test_selected_apple_source_strings_not_compilation(modules, hint, suffix, prefix, arch):
    module = modules["metal-build-runtime"]
    plan = module["example"]()
    plan.update(target_hint=hint, output_suffix=suffix, prefix_hint=prefix, macabi_arch=arch)
    result = module["audit"](plan)
    ios = hint.startswith(("iphone", "macabi"))
    expected_prefix = ("demo_model_q4f16_1_" if prefix == "auto" and ios else
                       prefix if hint in ("iphone", "macabi") else "")
    assert result["resolved_prefix_literal"] == expected_prefix
    assert bool(result["issues"]) == (ios and suffix != ".tar" or
                                      hint == "metal:x86-64" and suffix != ".dylib")
    if hint.startswith("macabi"):
        assert result["metal_compile_sdk_declaration"] == "macosx"
        assert result["preset_host_triple"] == (
            ("x86_64" if arch == "x86_64" else "arm64") + "-apple-ios18.0-macabi"
        )
    assert result["native_verification"] == result["compiler_check"] == "not_run"
    assert result["actual_artifact_abi_exports_and_format"] == "not_inspected"


def test_target_missing_static_prefix_is_warning_not_rejection(modules):
    module = modules["metal-build-runtime"]
    plan = module["example"]()
    plan["prefix_hint"] = "explicit_prefix"
    result = module["audit"](plan)
    assert not result["issues"]
    assert "literal_colon_hint_discards_explicit_prefix" in result["warnings"]
    assert "static_prefix_missing_source_warns_not_rejects" in result["warnings"]
    plan["target_hint"] = "iphone"
    assert module["audit"](plan)["resolved_prefix_literal"] == "explicit_prefix"


def test_kv_limit_clamp_minimum_and_compiled_workspace_inputs(modules):
    module = modules["runtime-kv-limits"]
    plan = module["example"]()
    result = module["audit"](plan)
    assert result["aggregate_limits"] == {
        "compiled_context_min": 4096, "runtime_context_min": 4096,
        "compiled_prefill_min": 512, "runtime_prefill_min": 128,
        "compiled_batch_min": 8, "runtime_sliding_window_min": 2048,
    }
    plan["models"][1]["runtime_prefill"] = 32
    result = module["audit"](plan)
    assert result["aggregate_limits"]["runtime_prefill_min"] == 32
    assert [r["workspace_prefill_from_compiled_config"] for r in result["models"]] == [1024, 512]
    assert result["allocation_or_capacity_estimate"] == "not_computed"
    assert result["effective_engine_configuration"] == "not_computed"
    assert result["physical_fit"] == "not_verified"


def test_kv_unbounded_context_and_required_finite_prefill_are_separate(modules):
    module = modules["runtime-kv-limits"]
    plan = module["example"]()
    for model in plan["models"]:
        model.update(compiled_context=-1, runtime_context=-1, compiled_prefill=-1,
                     runtime_prefill=-1, runtime_sliding_window=-1)
    result = module["audit"](plan)
    assert result["aggregate_limits"]["runtime_context_min"] is None
    assert len(result["issues"]) == 2
    plan["models"][1].update(compiled_prefill=128, runtime_prefill=-1)
    assert not module["audit"](plan)["issues"]
    plan["models"][0]["compiled_batch"] = True
    with pytest.raises(ValueError):
        module["audit"](plan)


@pytest.mark.parametrize("area", SCRIPTS)
@pytest.mark.parametrize("value", [None, True, [], {}, 1, "bad"])
def test_helpers_reject_invalid_top_level_shapes(modules, area, value):
    with pytest.raises(ValueError):
        modules[area]["audit"](value)


def call(area, args, tmp_path, data=None):
    script = ROOT / "sub-skills" / area / "scripts" / SCRIPTS[area]
    return subprocess.run([sys.executable, str(script), *args], input=data,
                          capture_output=True, cwd=tmp_path, timeout=8)


@pytest.mark.parametrize("area", SCRIPTS)
def test_helper_cli_synthetic_roundtrip_and_fixed_private_errors(modules, area, tmp_path):
    module = modules[area]
    assert call(area, ["--help"], tmp_path).returncode == 0
    example = call(area, ["--example"], tmp_path)
    assert example.returncode == 0 and json.loads(example.stdout) == module["example"]()
    result = call(area, ["-"], tmp_path, example.stdout)
    assert result.returncode == 0
    path = tmp_path / "private-synthetic-sentinel.json"
    path.write_bytes(example.stdout)
    assert call(area, [str(path)], tmp_path).returncode == 0
    for args in ([str(path), str(path)], ["--example", str(path)], ["--bad-private-sentinel"],
                 [str(tmp_path / "private-synthetic-sentinel-missing")], [str(tmp_path)]):
        result = call(area, args, tmp_path)
        assert result.returncode == 2 and not result.stdout
        assert b"private-synthetic-sentinel" not in result.stderr
        assert b"Traceback" not in result.stderr
    if hasattr(os, "mkfifo"):
        fifo = tmp_path / "private-synthetic-sentinel.fifo"
        os.mkfifo(fifo)
        result = call(area, [str(fifo)], tmp_path)
        assert result.returncode == 2 and not result.stdout
        assert b"private-synthetic-sentinel" not in result.stderr


@pytest.mark.parametrize("area", SCRIPTS)
@pytest.mark.parametrize("raw", [b"{", b"NaN", b"\xff", b"[]", b" " * 70000,
                                  b"[" * 2000 + b"]" * 2000,
                                  b'{"schema_version":1,"schema_version":1}'])
def test_helper_cli_invalid_json_and_caps(area, raw, tmp_path):
    result = call(area, ["-"], tmp_path, raw)
    assert result.returncode == 2 and not result.stdout and b"Traceback" not in result.stderr
