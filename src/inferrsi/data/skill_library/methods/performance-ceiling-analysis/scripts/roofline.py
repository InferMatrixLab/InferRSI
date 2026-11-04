"""Pure, internal single-resource Roofline arithmetic; no execution or acceptance."""

import math

FLOAT_DTYPES = {
    "float64", "float32", "tf32", "float16", "bfloat16", "float8_e4m3fn", "float8_e5m2",
}
OP_FIELDS = ("dtype", "accumulator_dtype", "op_class", "sparsity", "fma_flops")


def _copy_json(value):
    """Accept only JSON data, without invoking caller-defined copy/serialization hooks."""
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) is list:
        return [_copy_json(item) for item in value]
    if type(value) is dict and all(type(key) is str for key in value):
        return {key: _copy_json(item) for key, item in value.items()}
    raise ValueError("Inputs must contain only finite JSON data")


def _text(mapping, key, path, unknowns):
    value = mapping.get(key)
    if value is None or value == "":
        unknowns.append(f"{path}.{key}: missing")
        return None
    if type(value) is not str or not value.strip():
        raise ValueError(f"{path}.{key} must be nonempty text or null")
    return value


def _mapping(value, path):
    if value is None:
        return {}
    if type(value) is not dict:
        raise ValueError(f"{path} must be an object or null")
    return value


def _positive(value, path):
    if value is None:
        return None
    if type(value) not in (int, float):
        raise ValueError(f"{path} must be a finite positive number or null")
    try:
        result = float(value)
    except OverflowError as error:
        raise ValueError(f"{path} exceeds the numeric range") from error
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{path} must be a finite positive number or null")
    return result


def _source(value, path, unknowns):
    source = _mapping(value, path)
    kind = _text(source, "kind", path, unknowns)
    _text(source, "locator", path, unknowns)
    revision = source.get("revision")
    digest = source.get("sha256")
    if revision is not None:
        _text(source, "revision", path, unknowns)
    if digest is not None:
        if type(digest) is not str or len(digest) != 64 or any(
            char not in "0123456789abcdef" for char in digest
        ):
            raise ValueError(f"{path}.sha256 must be a lowercase SHA-256 digest")
    if not revision and not digest:
        unknowns.append(f"{path}: source revision or sha256 is missing")
    if source.get("recorded_at"):
        _text(source, "recorded_at", path, unknowns)
    else:
        _text(source, "time_unknown_reason", path, unknowns)
    return kind


def _fact(mapping, key, unit, path, unknowns):
    path = f"{path}.{key}"
    fact = _mapping(mapping.get(key), path)
    value = _positive(fact.get("value"), f"{path}.value")
    if value is None:
        unknowns.append(f"{path}.value: {fact.get('missing_reason') or 'missing'}")
    if _text(fact, "unit", path, unknowns) != unit:
        unknowns.append(f"{path}.unit: requires {unit}; no implicit conversion")
    kind = _source(fact.get("source"), f"{path}.source", unknowns)
    return value, fact, kind


def _operation(mapping, path, unknowns):
    operation = _mapping(mapping.get("operation"), f"{path}.operation")
    for key in OP_FIELDS[:-1]:
        _text(operation, key, f"{path}.operation", unknowns)
    for key in ("dtype", "accumulator_dtype"):
        if operation.get(key) not in FLOAT_DTYPES:
            unknowns.append(f"{path}.operation.{key}: unsupported floating-point dtype")
    if operation.get("op_class") not in ("scalar", "vector", "matrix"):
        unknowns.append(f"{path}.operation.op_class: requires one scalar/vector/matrix class")
    convention = operation.get("fma_flops")
    _positive(convention, f"{path}.operation.fma_flops")
    if convention not in (1, 2):
        unknowns.append(f"{path}.operation.fma_flops: requires an explicit 1 or 2 convention")
    return operation


def _finite(value, label):
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"Derived {label} is outside the finite positive numeric range")
    return value


def analyze(workload, hardware):
    """Return conditional arithmetic and retained inputs; see references/roofline-contract.md.

    Missing/incompatible evidence returns INSUFFICIENT_EVIDENCE. Malformed data
    raises ValueError. Neither result is a campaign verdict or permission to run.
    Hardware rates must both be rated references, or both synthetic fixtures.
    Empirical component envelopes are retained but not treated as L1 bounds.
    """
    workload = _mapping(_copy_json(workload), "workload")
    hardware = _mapping(_copy_json(hardware), "hardware")
    unknowns = []
    for key in ("workload_id", "shape", "boundary", "hardware_id", "resource_scope"):
        _text(workload, key, "workload", unknowns)
    operation = _operation(workload, "workload", unknowns)
    work, _, work_kind = _fact(workload, "work", "FLOP", "workload", unknowns)
    traffic, traffic_fact, traffic_kind = _fact(
        workload, "traffic", "byte", "workload", unknowns
    )
    tier = _text(traffic_fact, "tier", "workload.traffic", unknowns)
    if work_kind not in ("derived", "measured", "synthetic"):
        unknowns.append("workload.work.source.kind: requires derived/measured/synthetic counts")
    if traffic_kind not in ("derived", "measured", "synthetic"):
        unknowns.append("workload.traffic.source.kind: requires derived/measured/synthetic counts")
    intensity = _finite(work / traffic, "intensity") if not unknowns else None

    for key in ("hardware_id", "resource_scope"):
        value = _text(hardware, key, "hardware", unknowns)
        if value != workload.get(key):
            unknowns.append(f"hardware.{key}: differs from workload")
    count = hardware.get("device_count")
    _positive(count, "hardware.device_count")
    if type(count) is not int or count != 1:
        unknowns.append("hardware.device_count: only one device is supported")
    hardware_operation = _operation(hardware, "hardware", unknowns)
    for key in OP_FIELDS:
        if operation.get(key) != hardware_operation.get(key):
            unknowns.append(f"hardware.operation.{key}: differs from workload")
    compute, _, compute_kind = _fact(
        hardware, "peak_compute", "FLOP/s", "hardware", unknowns
    )
    bandwidth, bandwidth_fact, bandwidth_kind = _fact(
        hardware, "bandwidth", "byte/s", "hardware", unknowns
    )
    bandwidth_tier = _text(bandwidth_fact, "tier", "hardware.bandwidth", unknowns)
    if tier != bandwidth_tier:
        unknowns.append("hardware.bandwidth.tier: differs from workload traffic tier")
    basis = compute_kind if compute_kind == bandwidth_kind else None
    if basis not in ("rated", "synthetic"):
        unknowns.append("hardware rates: requires both rated or both synthetic sources; "
                        "probes/empirical envelopes are outside this L1 helper")
    assumptions = []
    for label, mapping in (("workload", workload), ("hardware", hardware)):
        values = mapping.get("assumptions")
        if values is None or values == []:
            unknowns.append(f"{label}.assumptions: missing")
        elif type(values) is not list or any(
            type(value) is not str or not value.strip() for value in values
        ):
            raise ValueError(f"{label}.assumptions must be a list of nonempty strings")
        else:
            assumptions.extend(values)
    roof = ridge = floor = limiting = None
    if not unknowns:
        compute_time = _finite(work / compute, "compute time")
        traffic_time = _finite(traffic / bandwidth, "traffic time")
        floor = max(compute_time, traffic_time)
        # Avoid overflowing intensity * bandwidth before applying the compute cap.
        roof = _finite(work / floor, "roof")
        ridge = _finite(compute / bandwidth, "ridge")
        limiting = ("balanced" if compute_time == traffic_time else
                    "compute" if compute_time > traffic_time else "memory")
    return {
        "analysis_status": "INSUFFICIENT_EVIDENCE" if unknowns else "COMPUTED",
        "evidence_basis": basis,
        "arithmetic_intensity_flop_per_byte": intensity,
        "conditional_roof_flop_per_s": roof,
        "ridge_flop_per_byte": ridge,
        "conditional_runtime_floor_s": floor,
        "analytical_limiting_factor": limiting,
        "assumptions": assumptions,
        "unknowns": unknowns,
        "inputs": {"workload": workload, "hardware": hardware},
        "limits": [
            "Conditional on supplied work/traffic, operation and resource facts; unverified here.",
            "No achievable utilization, speedup, quality, goal acceptance or E2E claim follows.",
            "Queueing, launch, synchronization and communication are not modeled.",
            "Changing algorithm, caching, sparsity or traffic changes this conditional model.",
        ],
    }
