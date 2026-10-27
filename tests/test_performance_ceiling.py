"""Synthetic arithmetic and evidence boundaries; no hardware performance claims."""

import builtins
import copy
import json
from pathlib import Path

import pytest

from inferrsi.knowledge_operations import KnowledgeReader

ROOT = Path(__file__).resolve().parents[1]
OWNER = ROOT / "src/inferrsi/data/skill_library/methods/performance-ceiling-analysis"
CODE = compile((OWNER / "scripts/roofline.py").read_text(encoding="utf-8"), "roofline.py", "exec")
NAMESPACE = {}
exec(CODE, NAMESPACE)
analyze = NAMESPACE["analyze"]


@pytest.fixture
def inputs():
    example = json.loads((OWNER / "references/roofline-example.json").read_text(encoding="utf-8"))
    return example["workload"], example["hardware"]


@pytest.mark.parametrize(
    "peak,roof,ridge,floor,limiting",
    [(100, 60, 10, 10, "memory"), (40, 40, 4, 15, "compute"), (60, 60, 6, 10, "balanced")],
)
def test_hand_calculated_cases(inputs, peak, roof, ridge, floor, limiting):
    workload, hardware = inputs
    hardware["peak_compute"]["value"] = peak
    result = analyze(workload, hardware)
    assert result["analysis_status"] == "COMPUTED"
    assert result["arithmetic_intensity_flop_per_byte"] == 6
    assert result["conditional_roof_flop_per_s"] == roof
    assert result["ridge_flop_per_byte"] == ridge
    assert result["conditional_runtime_floor_s"] == floor
    assert result["analytical_limiting_factor"] == limiting
    assert result["evidence_basis"] == "synthetic"
    assert result["unknowns"] == []


def test_bandwidth_cap_and_scaled_work(inputs):
    workload, hardware = inputs
    hardware["bandwidth"]["value"] = 20
    result = analyze(workload, hardware)
    assert result["conditional_roof_flop_per_s"] == 100
    assert result["conditional_runtime_floor_s"] == 6
    workload["work"]["value"] *= 2
    workload["traffic"]["value"] *= 2
    scaled = analyze(workload, hardware)
    assert scaled["conditional_roof_flop_per_s"] == result["conditional_roof_flop_per_s"]
    assert scaled["conditional_runtime_floor_s"] == 12


@pytest.mark.parametrize(
    "path,value,reason",
    [
        (("hardware", "bandwidth", "unit"), "GB/s", "unit"),
        (("hardware", "peak_compute", "unit"), "OPS/s", "unit"),
        (("workload", "work", "unit"), "MAC", "unit"),
        (("hardware", "bandwidth", "tier"), "L2", "tier"),
        (("hardware", "operation", "dtype"), "float16", "dtype"),
        (("hardware", "operation", "accumulator_dtype"), "float64", "accumulator_dtype"),
        (("hardware", "operation", "op_class"), "vector", "op_class"),
        (("hardware", "operation", "sparsity"), "2:4", "sparsity"),
        (("hardware", "operation", "fma_flops"), 1, "fma_flops"),
        (("hardware", "resource_scope"), "logical-device-1", "resource_scope"),
        (("hardware", "hardware_id"), "other-reference", "hardware_id"),
        (("hardware", "device_count"), 2, "one device"),
        (("workload", "operation", "dtype"), "int8", "unsupported"),
        (("workload", "operation", "op_class"), "mixed", "one scalar"),
        (("hardware", "peak_compute", "source", "locator"), None, "locator"),
        (("hardware", "peak_compute", "source", "revision"), None, "revision"),
        (("hardware", "peak_compute", "source", "time_unknown_reason"), None, "time_unknown"),
        (("hardware", "peak_compute", "value"), None, "value"),
        (("workload", "traffic", "value"), None, "value"),
        (("hardware", "assumptions"), [], "assumptions"),
        (("workload", "boundary"), None, "boundary"),
    ],
)
def test_incompatible_or_unknown_evidence(inputs, path, value, reason):
    document = dict(zip(("workload", "hardware"), inputs))
    target = document
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    result = analyze(**document)
    assert result["analysis_status"] == "INSUFFICIENT_EVIDENCE"
    assert result["conditional_roof_flop_per_s"] is None
    assert result["conditional_runtime_floor_s"] is None
    assert result["analytical_limiting_factor"] is None
    assert any(reason in item for item in result["unknowns"])


def test_missing_hardware_retains_independent_ai_and_unknown_reason(inputs):
    workload, hardware = inputs
    hardware["peak_compute"]["value"] = None
    hardware["peak_compute"]["missing_reason"] = "No matching rated source"
    result = analyze(workload, hardware)
    assert result["arithmetic_intensity_flop_per_byte"] == 6
    assert any("No matching rated source" in item for item in result["unknowns"])
    assert analyze(workload, None)["conditional_roof_flop_per_s"] is None


@pytest.mark.parametrize("kind", ["measured", "probed"])
def test_empirical_envelope_and_probe_are_not_rated_bounds(inputs, kind):
    workload, hardware = inputs
    for key in ("peak_compute", "bandwidth"):
        hardware[key]["source"]["kind"] = kind
    result = analyze(workload, hardware)
    assert result["analysis_status"] == "INSUFFICIENT_EVIDENCE"
    assert result["evidence_basis"] == kind
    assert result["conditional_runtime_floor_s"] is None
    assert result["inputs"]["hardware"]["bandwidth"]["source"]["kind"] == kind


def test_rated_and_mixed_sources_remain_distinct(inputs):
    workload, hardware = inputs
    hardware["peak_compute"]["source"]["kind"] = "rated"
    assert analyze(workload, hardware)["evidence_basis"] is None
    hardware["bandwidth"]["source"]["kind"] = "rated"
    result = analyze(workload, hardware)
    assert result["analysis_status"] == "COMPUTED"
    assert result["evidence_basis"] == "rated"
    assert "verdict" not in result and "speedup" not in result


@pytest.mark.parametrize("bad", [0, -1, True, False, "100", float("nan"), float("inf"), 10**400])
@pytest.mark.parametrize("side,key", [
    ("workload", "work"), ("workload", "traffic"),
    ("hardware", "peak_compute"), ("hardware", "bandwidth"),
])
def test_invalid_numbers_are_rejected_even_with_other_missing_evidence(inputs, side, key, bad):
    document = dict(zip(("workload", "hardware"), inputs))
    document[side][key]["value"] = bad
    document["hardware"]["peak_compute"]["source"] = None
    with pytest.raises(ValueError):
        analyze(**document)


def test_finite_extremes_and_derived_range_errors(inputs):
    workload, hardware = inputs
    workload["work"]["value"] = 1e300
    workload["traffic"]["value"] = 1e100
    hardware["peak_compute"]["value"] = 1e100
    hardware["bandwidth"]["value"] = 1e200
    assert analyze(workload, hardware)["conditional_roof_flop_per_s"] == pytest.approx(1e100)
    workload["traffic"]["value"] = 1e-100
    with pytest.raises(ValueError, match="Derived intensity"):
        analyze(workload, hardware)


def test_provenance_determinism_and_no_input_or_output_aliasing(inputs):
    before = copy.deepcopy(inputs)
    first = analyze(*inputs)
    assert first == analyze(*inputs)
    assert inputs == before
    assert first["inputs"] == dict(zip(("workload", "hardware"), before))
    first["inputs"]["hardware"]["bandwidth"]["source"]["locator"] = "changed-output"
    assert inputs == before
    json.dumps(analyze(*inputs), allow_nan=False)


def test_loading_and_calculation_have_no_io_or_optional_imports(inputs):
    original_import = builtins.__import__
    imports = []

    def import_math_only(name, *args, **kwargs):
        imports.append(name)
        assert name == "math", f"Unexpected dependency or side-effect path: {name}"
        return original_import(name, *args, **kwargs)

    def no_open(*args, **kwargs):
        raise AssertionError("Pure helper attempted file I/O")

    restricted = dict(vars(builtins), __import__=import_math_only, open=no_open)
    namespace = {"__builtins__": restricted}
    exec(CODE, namespace)
    assert namespace["analyze"](*inputs)["analysis_status"] == "COMPUTED"
    assert imports == ["math"]


def test_owner_resources_are_readable_at_exact_checkout_revision(monkeypatch):
    reader = KnowledgeReader(skill_root=ROOT / "src/inferrsi/data/skill_library")
    reference = "checkout:performance-ceiling-analysis"
    # Discovery is covered by reader tests; scope this check to the selected owner.
    monkeypatch.setattr(reader, "owners", lambda: {"performance-ceiling-analysis": ["checkout"]})
    bundle = reader.read(reference)
    for relative in (
        "scripts/roofline.py",
        "references/roofline-contract.md",
        "references/roofline-example.json",
    ):
        resource = "methods/performance-ceiling-analysis/" + relative
        assert bundle.content[resource] == (OWNER / relative).read_bytes()
    assert reader.resource(reference, "methods/performance-ceiling-analysis/scripts/roofline.py",
                           revision=bundle.revision) == (OWNER / "scripts/roofline.py").read_bytes()
