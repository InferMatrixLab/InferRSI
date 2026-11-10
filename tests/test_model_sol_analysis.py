"""Synthetic arithmetic and evidence boundaries; no model, device or performance claims."""

import builtins
import copy
import json
import random
from pathlib import Path

import pytest

from inferrsi.knowledge_operations import KnowledgeReader

ROOT = Path(__file__).resolve().parents[1]
OWNER = ROOT / "src/inferrsi/data/skill_library/methods/model-sol-analysis"
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
                       "bound_demand": {"link.tp": 2.5},
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
        assert any(reason in unknown
                   for unknown in phase_floors(phase, hardware)["unknowns"])


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
                                         for key, value in demand.items()
                                         if generator.random() < 0.5}})
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


def test_owner_resources_are_readable_at_exact_checkout_revision(monkeypatch):
    reader = KnowledgeReader(skill_root=ROOT / "src/inferrsi/data/skill_library")
    reference = "checkout:model-sol-analysis"
    # Discovery is covered by reader tests; scope this check to the selected owner.
    monkeypatch.setattr(reader, "owners", lambda: {"model-sol-analysis": ["checkout"]})
    bundle = reader.read(reference)
    for relative in (
        "scripts/model_sol.py",
        "references/model-sol-contract.md",
        "references/model-sol-example.json",
    ):
        resource = "methods/model-sol-analysis/" + relative
        assert bundle.content[resource] == (OWNER / relative).read_bytes()
    helper = "methods/model-sol-analysis/scripts/model_sol.py"
    assert reader.resource(reference, helper, revision=bundle.revision) == (
        OWNER / "scripts/model_sol.py"
    ).read_bytes()
