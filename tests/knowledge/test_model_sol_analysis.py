"""Synthetic arithmetic and evidence boundaries; no model, device or performance claims."""

import builtins
import copy
import json
import random
import subprocess
import sys
from pathlib import Path

import pytest

from inferrsi.knowledge.knowledge_operations import KnowledgeReader

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "src/inferrsi/knowledge/data/skill_library"
OWNER = LIBRARY / "playbooks/measurement/model-sol-analysis"
CODE = compile((OWNER / "scripts/model_sol.py").read_text(encoding="utf-8"), "model_sol.py", "exec")
NAMESPACE = {}
exec(CODE, NAMESPACE)
join_checkpoint = NAMESPACE["join_checkpoint"]
kv_cache_bytes = NAMESPACE["kv_cache_bytes"]
phase_floors = NAMESPACE["phase_floors"]
SYNTHETIC = {"kind": "synthetic", "locator": "test"}


@pytest.fixture
def example():
    return json.loads((OWNER / "references/model-sol-example.json").read_text(encoding="utf-8"))


def test_hand_calculated_example(example):
    join = join_checkpoint(example["header"], example["inventory"])
    assert join["analysis_status"] == "COMPUTED"
    assert join["join_clean"] is True
    assert join["byte_checksum"] == {"header_bytes": 480, "inventory_bytes": 480, "equal": True}
    assert join["unclaimed_header_tensors"] == join["absent_stored_names"] == []

    decode = phase_floors(example["decode"], example["hardware"])
    assert decode["analysis_status"] == "COMPUTED"
    assert decode["resource_totals"] == {"compute.bf16": 120, "memory.hbm": 60, "link.tp": 10}
    assert decode["conditional_bound_s"] == 6
    assert decode["binding_resources"] == ["memory.hbm"]
    assert decode["serial_estimate_s"] == 8
    assert [(op["name"], op["time_s"], op["binding"]) for op in decode["per_op"]] == [
        ("attention block", 1, ["memory.hbm"]),
        ("mlp block", 2, ["memory.hbm"]),
        ("tensor-parallel all-reduce", 1, ["link.tp"]),
    ]
    assert decode["tokens_per_s_at_bound"] == pytest.approx(1 / 6)
    assert decode["tokens_per_s_at_serial_estimate"] == pytest.approx(1 / 8)

    kv = kv_cache_bytes(example["kv_layers"], 10)
    assert kv["total_bytes"] == 160 + 64
    assert kv["bounded_as_context_grows"] is False
    assert [group["positions"] for group in kv["groups"]] == [10, 4]


def test_join_reports_both_residuals(example):
    header, inventory = example["header"], example["inventory"]
    inventory["tensors"] = [row for row in inventory["tensors"] if "qkv_proj" not in row["name"]]
    inventory["tensors"].append({"name": "model.layers.X.mlp.router.weight", "dtype": "BF16",
                                 "shape": [2, 4], "copies": 2})
    result = join_checkpoint(header, inventory)
    assert result["analysis_status"] == "COMPUTED"
    assert result["join_clean"] is False
    assert result["unclaimed_header_tensors"] == [
        "model.layers.0.self_attn.qkv_proj.weight",
        "model.layers.1.self_attn.qkv_proj.weight",
    ]
    assert result["absent_stored_names"] == ["model.layers.X.mlp.router.weight"]


def test_byte_checksum_passes_where_the_join_fails(example):
    # Swap the widths of two submodules: per-name counts break, the byte total does not.
    for row in example["inventory"]["tensors"]:
        if "qkv_proj" in row["name"]:
            row.update(dtype="F8_E4M3", shape=[12, 8])
        elif row["name"].endswith("down_proj.weight"):
            row.update(dtype="BF16", shape=[4, 8])
    result = join_checkpoint(example["header"], example["inventory"])
    assert result["byte_checksum"]["equal"] is True
    assert result["join_clean"] is False
    assert result["mismatched_names"] == [
        "model.layers.X.mlp.down_proj.weight",
        "model.layers.X.self_attn.qkv_proj.weight",
    ]


def test_shared_names_are_summed_and_missing_copies_show_as_count_mismatch(example):
    for row in example["inventory"]["tensors"]:
        if "qkv_proj" in row["name"]:
            row["copies"] = 1
    result = join_checkpoint(example["header"], example["inventory"])
    qkv = next(row for row in result["matched"] if "qkv_proj" in row["name"])
    assert (qkv["header_tensors"], qkv["header_elements"], qkv["inventory_elements"]) == (2, 96, 48)
    assert qkv["element_diff"] == 48
    assert result["join_clean"] is False


def test_distinct_stored_names_must_not_claim_the_same_header_tensor():
    name = "layers.0.weight"
    tensor = {"dtype": "F32", "shape": [2]}
    header = {"source": SYNTHETIC, "tensors": {name: tensor}}
    inventory = {"source": SYNTHETIC, "tensors": [
        {"name": "layers.X.weight", **tensor}, {"name": name, **tensor},
    ]}
    result = join_checkpoint(header, inventory)
    assert result["analysis_status"] == "COMPUTED"
    assert result["join_clean"] is False
    assert result["multiply_claimed_header_tensors"] == [name]
    assert result["unclaimed_header_tensors"] == result["mismatched_names"] == []


@pytest.mark.parametrize("side", ["header", "inventory"])
@pytest.mark.parametrize("omit_shape", [True, False])
def test_join_requires_shape_evidence(side, omit_shape):
    header = {"source": SYNTHETIC, "tensors": {"w": {"dtype": "F32", "shape": []}}}
    inventory = {"source": SYNTHETIC, "tensors": [{"name": "w", "dtype": "F32", "shape": []}]}
    scalar = join_checkpoint(header, inventory)
    assert scalar["join_clean"]
    assert scalar["byte_checksum"]["header_bytes"] == 4

    row = header["tensors"]["w"] if side == "header" else inventory["tensors"][0]
    if omit_shape:
        row.pop("shape")
    else:
        row["shape"] = None
    result = join_checkpoint(header, inventory)
    assert result["analysis_status"] == "INSUFFICIENT_EVIDENCE"
    assert result["join_clean"] is False
    assert any(reason.startswith(side) and reason.endswith(".shape: missing")
               for reason in result["unknowns"])
    assert result["byte_checksum"][f"{side}_bytes"] is None
    assert result["byte_checksum"]["equal"] is None


def test_index_placeholder_matches_digits_and_segment_count_only(example):
    header = example["header"]
    header["tensors"]["model.layers.extra.self_attn.qkv_proj.weight"] = {"dtype": "BF16",
                                                                         "shape": [1]}
    header["tensors"]["model.layers.0.0.self_attn.qkv_proj.weight"] = {"dtype": "BF16",
                                                                       "shape": [1]}
    result = join_checkpoint(header, example["inventory"])
    assert result["unclaimed_header_tensors"] == [
        "model.layers.0.0.self_attn.qkv_proj.weight",
        "model.layers.extra.self_attn.qkv_proj.weight",
    ]


def test_buffers_count_only_when_stored(example):
    header, inventory = example["header"], example["inventory"]
    assert join_checkpoint(header, inventory)["absent_stored_names"] == []
    header["tensors"]["model.rotary_emb.inv_freq"] = {"dtype": "F32", "shape": [2]}
    result = join_checkpoint(header, inventory)
    assert result["byte_checksum"] == {"header_bytes": 488, "inventory_bytes": 488, "equal": True}
    assert result["join_clean"] is True


@pytest.mark.parametrize(
    "mutate,reason",
    [
        (lambda h, i: h.update(tensors={}), "header.tensors: empty"),
        (lambda h, i: h["tensors"]["lm_head.weight"].update(dtype="F4"), "no known byte width"),
        (lambda h, i: i["tensors"][0].update(dtype="NF4"), "bytes cannot be formed"),
        (lambda h, i: h.update(source={"kind": "derived", "locator": "x"}), "measured/synthetic"),
        (lambda h, i: i.pop("source"), "inventory.source.kind: missing"),
    ],
)
def test_join_unknowns_are_reported_not_guessed(example, mutate, reason):
    mutate(example["header"], example["inventory"])
    result = join_checkpoint(example["header"], example["inventory"])
    assert result["analysis_status"] == "INSUFFICIENT_EVIDENCE"
    assert result["join_clean"] is False
    assert any(reason in unknown for unknown in result["unknowns"])


@pytest.mark.parametrize(
    "path,value,reason",
    [
        (("rates", "memory.hbm", "source", "kind"), "measured", "peak/synthetic"),
        (("rates", "memory.hbm", "source", "kind"), "rated", "peak/synthetic"),
        (("rates", "memory.hbm", "source", "kind"), "peak", "all peak or all synthetic"),
        (("rates", "memory.hbm", "unit"), "GB/s", "no implicit conversion"),
        (("rates", "link.tp", "resource"), "pcie", "requires one of"),
        (("rates", "compute.bf16", "value"), None, "value: missing"),
        (("hardware_id",), "other", "differs from phase"),
        (("assumptions",), [], "hardware.assumptions: missing"),
    ],
)
def test_rate_evidence_boundaries(example, path, value, reason):
    target = example["hardware"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    result = phase_floors(example["decode"], example["hardware"])
    assert result["analysis_status"] == "INSUFFICIENT_EVIDENCE"
    assert result["conditional_bound_s"] is None and result["serial_estimate_s"] is None
    assert any(reason in unknown for unknown in result["unknowns"])


def test_phase_input_boundaries(example):
    phase = example["decode"]
    phase["ops"][0]["demand"]["memory.l2"] = 1
    phase["ops"][1]["source"] = {"kind": "guessed", "locator": "x"}
    phase["phase"] = "training"
    result = phase_floors(phase, example["hardware"])
    assert result["analysis_status"] == "INSUFFICIENT_EVIDENCE"
    joined = "\n".join(result["unknowns"])
    for reason in ("memory.l2: no matching hardware rate", "derived/measured/synthetic",
                   "phase.phase: requires one of prefill/decode"):
        assert reason in joined


@pytest.mark.parametrize("missing_fabric", ["link.tp", "link.inter"])
def test_transfer_requires_a_rate_for_each_fabric(example, missing_fabric):
    phase, hardware = example["decode"], example["hardware"]
    hardware["rates"]["link.inter"] = {
        "resource": "link", "unit": "byte/s", "value": 5, "source": SYNTHETIC,
    }
    phase["ops"][2]["demand"]["link.inter"] = 10
    del hardware["rates"][missing_fabric]
    result = phase_floors(phase, hardware)
    assert result["analysis_status"] == "INSUFFICIENT_EVIDENCE"
    assert result["conditional_bound_s"] is result["serial_estimate_s"] is None
    assert any(f"{missing_fabric}: no matching hardware rate" in reason
               for reason in result["unknowns"])

    phase["layout"] = "single rank"
    del phase["ops"][2]
    hardware["rates"].pop("link.inter" if missing_fabric == "link.tp" else "link.tp")
    assert phase_floors(phase, hardware)["analysis_status"] == "COMPUTED"


@pytest.mark.parametrize("fabric", ["link.tp", "link.inter"])
@pytest.mark.parametrize("bandwidth,snapshot", [
    (None, None), (0, 0), (-1, -1), (float("nan"), None), (float("inf"), None),
    (-float("inf"), None),
])
def test_unavailable_bandwidth_depends_on_actual_transfer(example, fabric, bandwidth, snapshot):
    phase, hardware = example["decode"], example["hardware"]
    hardware["rates"]["link.inter"] = dict(hardware["rates"]["link.tp"])
    fact = hardware["rates"][fabric]
    fact["value"] = bandwidth
    phase["ops"][2]["demand"]["link.inter"] = 5
    phase["ops"][2]["bound_demand"]["link.inter"] = 5

    result = phase_floors(phase, hardware)
    assert result["analysis_status"] == "INSUFFICIENT_EVIDENCE"
    assert result["actual_resource_totals"][fabric] == 10
    assert result["conditional_bound_s"] is result["serial_estimate_s"] is None
    assert result["tokens_per_s_at_bound"] is result["tokens_per_s_at_serial_estimate"] is None
    assert any(f"hardware.rates.{fabric}.value" in reason for reason in result["unknowns"])
    assert fact["value"] is bandwidth
    assert result["inputs"]["hardware"]["rates"][fabric]["value"] == snapshot
    json.dumps(result, allow_nan=False)

    other_fabric = "link.inter" if fabric == "link.tp" else "link.tp"
    phase["ops"][2]["demand"][fabric] = phase["ops"][2]["bound_demand"][fabric] = 0
    one_fabric = phase_floors(phase, hardware)
    assert one_fabric["analysis_status"] == "COMPUTED"
    assert one_fabric["per_op"][2]["binding"] == [other_fabric]

    # In a one-rank layout the same local copy has zero bytes on this fabric.
    local = dict(phase, layout="single rank", ops=[{
        "name": "local copy", "demand": {"memory.hbm": 10, fabric: 0},
        "bound_demand": {"memory.hbm": 10}, "source": SYNTHETIC,
    }])
    no_transfer = phase_floors(local, hardware)
    assert no_transfer["analysis_status"] == "COMPUTED"
    assert no_transfer["actual_resource_totals"][fabric] == 0
    assert no_transfer["serial_estimate_s"] == no_transfer["conditional_bound_s"] == 1


def test_latency_and_launch_floors_enter_the_serial_estimate_only(example):
    phase = example["decode"]
    latency = {"value": 3.0, "source": {"kind": "assumed", "locator": "unmeasured link latency"}}
    phase["ops"][2]["link_latency_s"] = latency
    phase["ops"].append({"name": "kernel launch", "repeat": 4, "source": SYNTHETIC,
                         "launch_floor_s": {"value": 0.5, "source": SYNTHETIC}})
    phase["ops"].append({"name": "barrier", "source": SYNTHETIC,
                         "link_latency_s": {"value": 0.25, "source": SYNTHETIC}})
    result = phase_floors(phase, example["hardware"])
    assert result["analysis_status"] == "COMPUTED"
    assert result["conditional_bound_s"] == 6
    # Latency adds to the all-reduce's 1 s of bytes (twice); four 0.5 s launches; one barrier.
    assert result["serial_estimate_s"] == 8 + 2 * 3 + 2 + 0.25
    assert [op["binding"] for op in result["per_op"][2:]] == [
        ["link.tp"], ["launch_floor"], ["link_latency"]]
    assert result["per_op"][2]["time_s"] == 4
    latency["source"]["kind"] = "rated"
    rejected = phase_floors(phase, example["hardware"])
    assert any("link_latency_s.source.kind" in unknown for unknown in rejected["unknowns"])


def test_link_phases_add_and_bound_demand_stays_irreducible(example):
    hardware = example["hardware"]
    hardware["rates"]["link.inter"] = {"resource": "link", "unit": "byte/s", "value": 1,
                                       "source": SYNTHETIC}
    phase = example["decode"]
    # A hierarchical all-reduce: intra phases on link.tp, one inter phase on link.inter.
    phase["ops"][2] = {"name": "hierarchical all-reduce", "repeat": 2, "source": SYNTHETIC,
                       "demand": {"link.tp": 5, "link.inter": 2},
                       "bound_demand": {"link.tp": 2.5, "link.inter": 2},
                       "link_latency_s": {"value": 0.5, "source": SYNTHETIC}}
    result = phase_floors(phase, hardware)
    assert result["analysis_status"] == "COMPUTED"
    assert result["per_op"][2]["time_s"] == 5 / 5 + 2 / 1 + 0.5
    assert result["per_op"][2]["binding"] == ["link.inter", "link.tp"]
    assert result["resource_totals"]["link.tp"] == 5
    assert result["actual_resource_totals"]["link.tp"] == 10
    assert result["conditional_bound_s"] == 6
    assert result["serial_estimate_s"] == 2 + 4 + 2 * 3.5
    for bad, reason in (({"link.tp": 6}, "exceeds demand"), ({"memory.hbm": 1}, "not in demand")):
        phase["ops"][2]["bound_demand"] = bad
        invalid = phase_floors(phase, hardware)
        assert any(reason in unknown for unknown in invalid["unknowns"])
        assert invalid["conditional_bound_s"] is None
        assert invalid["serial_estimate_s"] == result["serial_estimate_s"]


def test_peak_rates_state_their_clock_basis(example):
    rates = example["hardware"]["rates"]
    for rate in rates.values():
        rate["source"]["kind"] = "peak"
    result = phase_floors(example["decode"], example["hardware"])
    assert result["analysis_status"] == "INSUFFICIENT_EVIDENCE"
    assert sum("clock_basis: missing" in unknown for unknown in result["unknowns"]) == 3
    for rate in rates.values():
        rate["clock_basis"] = "sustained clock for this work, from the cited source"
    result = phase_floors(example["decode"], example["hardware"])
    assert (result["analysis_status"], result["evidence_basis"]) == ("COMPUTED", "peak")
    for rate in rates.values():
        rate["source"]["kind"] = "rated"
    assert phase_floors(example["decode"], example["hardware"])["evidence_basis"] is None


def test_fractional_effective_tokens_per_step(example):
    example["decode"]["tokens_per_step"] = 1.75
    result = phase_floors(example["decode"], example["hardware"])
    assert result["tokens_per_s_at_bound"] == pytest.approx(1.75 / 6)
    example["decode"].pop("tokens_per_step")
    missing = phase_floors(example["decode"], example["hardware"])
    assert "phase.tokens_per_step: missing" in missing["unknowns"]


@pytest.mark.parametrize("overflow", ["bound throughput", "serial throughput"])
def test_phase_rejects_nonfinite_derived_throughput(example, overflow):
    phase = example["decode"]
    phase["tokens_per_step"] = 1e308
    phase["ops"] = [{
        "name": "tiny demand", "demand": {"memory.hbm": 1e-308}, "source": SYNTHETIC,
        "bound_demand": {"memory.hbm": 0 if overflow == "serial throughput" else 1e-308},
    }]
    with pytest.raises(ValueError, match=overflow):
        phase_floors(phase, example["hardware"])


def test_phase_checks_resource_totals_even_with_incomplete_evidence(example):
    phase = example["decode"]
    phase.pop("assumptions")
    phase["ops"][0].update(demand={"compute.bf16": 1e308}, repeat=2)
    with pytest.raises(ValueError, match="actual resource demand"):
        phase_floors(phase, example["hardware"])


@pytest.mark.parametrize("basis", ["peak", "synthetic"])
@pytest.mark.parametrize("declaration,expected_s", [
    ({}, None),
    ({"bound_demand": None}, None),
    ({"bound_demand": {}}, None),
    ({"bound_demand": {"memory.hbm": None}}, None),
    ({"bound_demand": {"memory.hbm": 100}}, 1),
    ({"bound_demand": {"memory.hbm": 0}}, 0),
])
def test_schedule_traffic_needs_explicit_bound_evidence(example, basis, declaration, expected_s):
    phase, hardware = example["decode"], example["hardware"]
    hardware["rates"] = {"memory.hbm": {
        "resource": "memory", "unit": "byte/s", "value": 100,
        "source": {"kind": basis, "locator": "fixture peak"}, "clock_basis": "fixture clock",
    }}
    phase["ops"] = [{"name": "unfused copy", "source": SYNTHETIC,
                     "demand": {"memory.hbm": 400}, **declaration}]
    result = phase_floors(phase, hardware)
    assert result["serial_estimate_s"] == result["per_op"][0]["time_s"] == 4
    assert result["tokens_per_s_at_serial_estimate"] == 0.25
    assert result["actual_resource_totals"] == {"memory.hbm": 400}
    assert result["conditional_bound_s"] == expected_s
    if expected_s is None:
        assert result["analysis_status"] == "INSUFFICIENT_EVIDENCE"
        assert result["resource_totals"]["memory.hbm"] is None
        assert result["binding_resources"] is result["tokens_per_s_at_bound"] is None
        assert any("bound_demand.memory.hbm" in message for message in result["unknowns"])
    else:
        assert result["analysis_status"] == "COMPUTED"
        assert result["resource_totals"]["memory.hbm"] == 100 * expected_s
        assert result["binding_resources"] == ["memory.hbm"]
        assert result["tokens_per_s_at_bound"] == (1 if expected_s else None)


def test_incomplete_resource_across_ops_preserves_other_proven_totals(example):
    phase, hardware = example["decode"], example["hardware"]
    phase["ops"][0]["bound_demand"] = {"compute.bf16": 40}
    result = phase_floors(phase, hardware)
    assert result["resource_totals"] == {"compute.bf16": 120, "memory.hbm": None, "link.tp": 10}
    assert result["conditional_bound_s"] is None
    assert result["serial_estimate_s"] == 8


def test_resource_total_bound_survives_serial_repartition(example):
    phase, hardware = example["decode"], example["hardware"]
    compute = 10 * hardware["rates"]["compute.bf16"]["value"]
    memory = 10 * hardware["rates"]["memory.hbm"]["value"]
    phase["ops"] = [
        {"name": "compute", "demand": {"compute.bf16": compute},
         "bound_demand": {"compute.bf16": compute}, "source": SYNTHETIC},
        {"name": "memory", "demand": {"memory.hbm": memory},
         "bound_demand": {"memory.hbm": memory}, "source": SYNTHETIC},
    ]
    separate = phase_floors(phase, hardware)
    phase["ops"] = [{
        "name": "combined", "demand": {"compute.bf16": compute, "memory.hbm": memory},
        "bound_demand": {"compute.bf16": compute, "memory.hbm": memory}, "source": SYNTHETIC,
    }]
    combined = phase_floors(phase, hardware)
    assert separate["conditional_bound_s"] == combined["conditional_bound_s"] == 10
    assert separate["serial_estimate_s"] == 20
    assert combined["serial_estimate_s"] == 10


def test_bound_never_exceeds_serial_estimate():
    generator = random.Random(1103)
    rates = {name: {"resource": resource, "unit": unit, "value": generator.uniform(1, 50),
                    "source": SYNTHETIC}
             for name, resource, unit in (("c", "compute", "FLOP/s"), ("m", "memory", "byte/s"),
                                          ("l", "link", "byte/s"), ("x", "link", "byte/s"))}
    hardware = {"hardware_id": "h", "assumptions": ["synthetic"], "rates": rates}
    for _ in range(200):
        ops = []
        for index in range(generator.randint(1, 6)):
            demand = {key: generator.uniform(0, 100) for key in rates
                      if generator.random() < 0.7} or {"c": 1.0}
            ops.append({"name": f"op{index}", "repeat": generator.randint(1, 4),
                        "source": SYNTHETIC, "demand": demand,
                        "bound_demand": {key: value * generator.random()
                                         for key, value in demand.items()}})
        phase = {"phase": "prefill", "model_id": "m", "layout": "l", "hardware_id": "h",
                 "tokens_per_step": 8, "assumptions": ["synthetic"], "ops": ops}
        result = phase_floors(phase, hardware)
        assert result["conditional_bound_s"] <= result["serial_estimate_s"] * (1 + 1e-12)


@pytest.mark.parametrize(
    "group,reason",
    [
        ({"name": "g", "layers": 1, "law": "sparse", "bytes_per_position": 1}, "law: requires"),
        ({"name": "g", "layers": 1, "law": "global"}, "bytes_per_position: missing"),
        ({"name": "g", "layers": 1, "law": "constant"}, "state_bytes: missing"),
        ({"name": "g", "layers": 1, "law": "window", "bytes_per_position": 1}, "window: missing"),
        ({"name": "g", "layers": 1, "law": "compressed", "bytes_per_position": 1},
         "ratio: missing"),
        ({"name": "g", "law": "global", "bytes_per_position": 1}, "layers: missing"),
    ],
)
def test_kv_unknowns(group, reason):
    result = kv_cache_bytes([dict(group, source=SYNTHETIC)], 8)
    assert result["analysis_status"] == "INSUFFICIENT_EVIDENCE"
    assert result["total_bytes"] is None and result["bounded_as_context_grows"] is None
    assert any(reason in unknown for unknown in result["unknowns"])


@pytest.mark.parametrize("layers", [[], None])
def test_kv_requires_layer_groups(layers):
    result = kv_cache_bytes(layers, 10)
    assert result["analysis_status"] == "INSUFFICIENT_EVIDENCE"
    assert result["total_bytes"] is result["bounded_as_context_grows"] is None
    assert result["unknowns"] == ["layers: empty"]


def test_kv_growth_laws():
    groups = [
        {"name": "window", "layers": 2, "law": "window", "window": 4, "bytes_per_position": 8},
        {"name": "compressed", "layers": 1, "law": "compressed", "ratio": 4,
         "bytes_per_position": 8},
        {"name": "state", "layers": 3, "law": "constant", "state_bytes": 64},
    ]
    groups = [dict(group, source=SYNTHETIC) for group in groups]
    short, long = kv_cache_bytes(groups, 3), kv_cache_bytes(groups, 1000)
    assert [group["positions"] for group in short["groups"]] == [3, 1, None]
    assert [group["bytes"] for group in long["groups"]] == [64, 2000, 192]
    assert long["bounded_as_context_grows"] is False
    assert kv_cache_bytes([groups[0], groups[2]], 10 ** 6)["bounded_as_context_grows"] is True


@pytest.mark.parametrize(
    "call",
    [
        lambda e: join_checkpoint({"tensors": {"a": {"dtype": "F32", "shape": [-1]}}}, {}),
        lambda e: join_checkpoint(e["header"], {"tensors": [{"name": "a", "copies": 0}]}),
        lambda e: phase_floors(dict(e["decode"], tokens_per_step=0), e["hardware"]),
        lambda e: phase_floors(e["decode"],
                               dict(e["hardware"], rates={"c": {"value": float("nan")}})),
        lambda e: phase_floors(dict(e["decode"], ops=[{"name": "a", "demand": {"c": -1}}]),
                               e["hardware"]),
        lambda e: kv_cache_bytes([{"name": "w", "layers": 1, "law": "window", "window": 0,
                                   "bytes_per_position": 1}], 4),
        lambda e: kv_cache_bytes([], -1),
        lambda e: join_checkpoint({"tensors": {1: {}}}, {}),
    ],
)
def test_malformed_data_raises(example, call):
    with pytest.raises(ValueError):
        call(example)


def test_determinism_and_no_input_or_output_aliasing(example):
    before = copy.deepcopy(example)
    first = phase_floors(example["decode"], example["hardware"])
    assert first == phase_floors(example["decode"], example["hardware"])
    assert example == before
    first["inputs"]["hardware"]["rates"]["link.tp"]["source"]["locator"] = "changed-output"
    assert example == before
    for result in (first, join_checkpoint(example["header"], example["inventory"]),
                   kv_cache_bytes(example["kv_layers"], 10)):
        json.dumps(result, allow_nan=False)


def test_loading_and_calculation_have_no_io_or_optional_imports(example):
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
    assert namespace["phase_floors"](example["decode"], example["hardware"])["analysis_status"] \
        == "COMPUTED"
    assert namespace["join_checkpoint"](example["header"], example["inventory"])["join_clean"]
    assert imports == ["math"]


def test_owner_resources_are_readable_at_exact_checkout_revision():
    reader = KnowledgeReader(skill_root=LIBRARY)
    reference = "checkout:model-sol-analysis"
    bundle = reader.read(reference)
    for relative in (
        "scripts/model_sol.py",
        "references/model-sol-contract.md",
        "references/model-sol-example.json",
    ):
        resource = f"{OWNER.relative_to(LIBRARY).as_posix()}/{relative}"
        assert bundle.content[resource] == (OWNER / relative).read_bytes()
    helper = f"{OWNER.relative_to(LIBRARY).as_posix()}/scripts/model_sol.py"
    assert reader.resource(reference, helper, revision=bundle.revision) == (
        OWNER / "scripts/model_sol.py"
    ).read_bytes()


def test_datasheet_time_has_no_qualified_bound(example):
    for rate in example["hardware"]["rates"].values():
        rate["source"]["kind"] = "datasheet"
    # An explicit lower count or missing proof must not change the nominal cost
    # of the scheduled graph. H200's offline replay also supplies only demand.
    example["decode"]["ops"][0]["bound_demand"]["memory.hbm"] = 0
    del example["decode"]["ops"][1]["bound_demand"]
    result = phase_floors(example["decode"], example["hardware"])
    assert result["analysis_status"] == "COMPUTED"
    assert result["evidence_basis"] == "datasheet"
    assert result["datasheet_resource_time_s"] == 6
    assert result["datasheet_binding_resources"] == ["memory.hbm"]
    assert result["resource_totals"]["memory.hbm"] is None
    assert result["actual_resource_totals"]["memory.hbm"] == 60
    assert result["serial_estimate_s"] == 8
    assert result["conditional_bound_s"] is result["tokens_per_s_at_bound"] is None
    assert result["binding_resources"] is None
    del example["hardware"]["rates"]["link.tp"]
    partial = phase_floors(example["decode"], example["hardware"])
    assert partial["analysis_status"] == "INSUFFICIENT_EVIDENCE"
    assert partial["datasheet_resource_time_s"] is partial["serial_estimate_s"] is None


@pytest.mark.parametrize("length,complete,rounded", [(3, 0, 1), (4, 1, 1), (5, 1, 2)])
def test_complete_index_groups_and_separate_tail(length, complete, rounded):
    common = {"layers": 1, "ratio": 4, "bytes_per_position": 8, "source": SYNTHETIC}
    groups = [dict(common, name="complete", law="complete_groups"),
              dict(common, name="rounded", law="compressed")]
    result = kv_cache_bytes(groups, length)
    assert [row["positions"] for row in result["groups"]] == [complete, rounded]


def test_h200_tp4_pinned_analysis_from_cli():
    driver = OWNER / "scripts/qwen38_h200_tp4.py"
    result = json.loads(subprocess.check_output([sys.executable, str(driver)]))
    assert result["text_tensor_count"] == 1294
    weights = result["rank_weight_bytes_by_family"]
    assert weights["routed"] == 48 * 512 * 3 * 2560 * 640 * 2 // 4
    assert weights["ngram"] == 32 * 2_500_012 * 160 * 2
    cache = result["rank_cache_payload_bytes_after_prefill"]
    assert cache["QSA main K/V"] == 96 * 2**20
    assert cache["QSA raw index ring"] == 12 * 4 * 128 * 2
    assert cache["GDN recurrent matrix"] == 36 * (48 // 4) * 128**2 * 4
    narrow, wide = result["prefill"]
    assert narrow["demand_per_rank"]["compute.bf16"] == wide["demand_per_rank"]["compute.bf16"]
    assert (wide["demand_per_rank"]["memory.hbm"] - narrow["demand_per_rank"]["memory.hbm"]
            == weights["routed"] * (512 - 10) // 512)
    assert narrow["binding"] == wide["binding"] == ["compute.bf16"]
    assert result["decode_steps"] == 255
    first, last = result["first_decode"], result["last_decode"]
    assert (first["visible_tokens"], last["visible_tokens"]) == (8193, 8447)
    assert first["demand_per_rank"]["link.nvlink_tx"] == 96 * 2560 * 2 * 3 // 2
    assert first["binding"] == last["binding"] == ["memory.hbm"]
    assert result["mean_decode_resource_ms"] * result["decode_tokens_per_s_at_resource_max"] \
        == pytest.approx(1000)
    assert result["whole_model"]["qualified_bound_s"] is None
    single = json.loads(subprocess.check_output(
        [sys.executable, str(driver), "--prompt-tokens", "1", "--output-tokens", "1"],
    ))
    assert len(single["prefill"]) == 1
    assert single["decode_steps"] == 0 and single["first_decode"] is single["last_decode"] is None
