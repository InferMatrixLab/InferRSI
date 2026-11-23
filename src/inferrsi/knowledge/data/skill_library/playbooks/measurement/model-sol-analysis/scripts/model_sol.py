"""Pure model-level speed-of-light arithmetic over supplied counts.

No I/O, network access, device execution or acceptance. Every function takes
JSON data, returns JSON data and reports missing evidence as unknowns instead of
guessing. See references/model-sol-contract.md for inputs, outputs and limits.
"""

import math

# Byte widths of safetensors header dtypes. Packed sub-byte formats are stored in
# one of these containers, so the header's own dtype gives the physical width.
DTYPE_BYTES = {
    "F64": 8, "I64": 8, "U64": 8,
    "F32": 4, "I32": 4, "U32": 4,
    "F16": 2, "BF16": 2, "I16": 2, "U16": 2,
    "F8_E4M3": 1, "F8_E5M2": 1, "F8_E8M0": 1, "I8": 1, "U8": 1, "BOOL": 1,
}
PHASES = ("prefill", "decode")
KV_LAWS = ("global", "window", "compressed", "complete_groups", "constant")
RATE_UNITS = {"compute": "FLOP/s", "memory": "byte/s", "link": "byte/s"}
SOURCE_KINDS = ("derived", "measured", "synthetic")
RATE_KINDS = ("peak", "synthetic", "datasheet")
FLOOR_KINDS = ("measured", "assumed", "synthetic")


def _copy_json(value):
    """Accept only JSON data, without invoking caller-defined hooks."""
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) is list:
        return [_copy_json(item) for item in value]
    if type(value) is dict and all(type(key) is str for key in value):
        return {key: _copy_json(item) for key, item in value.items()}
    raise ValueError("Inputs must contain only finite JSON data")


def _mapping(value, path):
    if value is None:
        return {}
    if type(value) is not dict:
        raise ValueError(f"{path} must be an object or null")
    return value


def _list(value, path):
    if value is None:
        return []
    if type(value) is not list:
        raise ValueError(f"{path} must be a list or null")
    return value


def _text(mapping, key, path, unknowns):
    value = mapping.get(key)
    if value is None or value == "":
        unknowns.append(f"{path}.{key}: missing")
        return None
    if type(value) is not str or not value.strip():
        raise ValueError(f"{path}.{key} must be nonempty text or null")
    return value


def _count(value, path, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{path} must be an integer >= {minimum}")
    return value


def _required_count(mapping, key, path, unknowns):
    if mapping.get(key) is None:
        unknowns.append(f"{path}.{key}: missing")
        return None
    return _count(mapping.get(key), f"{path}.{key}", 1)


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


def _nonnegative(value, path):
    if type(value) not in (int, float):
        raise ValueError(f"{path} must be a finite number >= 0")
    try:
        result = float(value)
    except OverflowError as error:
        raise ValueError(f"{path} exceeds the numeric range") from error
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{path} must be a finite number >= 0")
    return result


def _finite(value, label):
    if not math.isfinite(value):
        raise ValueError(f"Derived {label} is outside the finite numeric range")
    return value


def _scaled(value, count, label):
    try:
        return _finite(value * count, label)
    except OverflowError as error:
        raise ValueError(f"Derived {label} is outside the finite numeric range") from error


def _source(value, path, unknowns, kinds):
    source = _mapping(value, path)
    kind = _text(source, "kind", path, unknowns)
    _text(source, "locator", path, unknowns)
    if kind is not None and kind not in kinds:
        unknowns.append(f"{path}.kind: requires one of {'/'.join(kinds)}")
    return kind


def _assumptions(mapping, path, unknowns):
    values = mapping.get("assumptions")
    if values is None or values == []:
        unknowns.append(f"{path}.assumptions: missing")
        return []
    if type(values) is not list or any(
        type(item) is not str or not item.strip() for item in values
    ):
        raise ValueError(f"{path}.assumptions must be a list of nonempty strings")
    return list(values)


def _tensor_counts(tensor, path, unknowns, copies=1):
    shape = tensor.get("shape")
    dtype = tensor.get("dtype")
    if dtype is not None and type(dtype) is not str:
        raise ValueError(f"{path}.dtype must be a string or null")
    width = DTYPE_BYTES.get(dtype)
    if width is None:
        unknowns.append(f"{path}.dtype: no known byte width; bytes cannot be formed")
    if shape is None:
        unknowns.append(f"{path}.shape: missing")
        return None, None
    total = 1
    for index, size in enumerate(_list(shape, f"{path}.shape")):
        total *= _count(size, f"{path}.shape[{index}]")
    elements = total * copies
    return elements, elements * width if width is not None else None


def _sum_known(values):
    total = 0
    for value in values:
        if value is None:
            return None
        total += value
    return total


def _selects(pattern, name):
    """A stored name selects a header name segment by segment; `X` matches any index."""
    wanted, actual = pattern.split("."), name.split(".")
    if len(wanted) != len(actual):
        return False
    return all(w == a or (w == "X" and a.isdigit()) for w, a in zip(wanted, actual))


def join_checkpoint(header, inventory):
    """Join an analytical stored-tensor inventory to a checkpoint header in both directions.

    `header.tensors` maps verbatim header names to {dtype, shape}, merged across
    shards. `inventory.tensors` lists stored tensors as {name, dtype, shape, copies,
    buffer}; a name may write `X` at an indexed position. Rows sharing a name are
    summed. Returns missing and multiply claimed names, per-name comparisons
    and the byte checksum. The join is the gate; the byte total is its checksum.
    """
    header = _mapping(_copy_json(header), "header")
    inventory = _mapping(_copy_json(inventory), "inventory")
    unknowns = []
    _source(header.get("source"), "header.source", unknowns, ("measured", "synthetic"))
    _source(inventory.get("source"), "inventory.source", unknowns, SOURCE_KINDS)

    tensors = {}
    for name, entry in _mapping(header.get("tensors"), "header.tensors").items():
        if name == "__metadata__":
            continue
        path = f"header.tensors.{name}"
        tensors[name] = _tensor_counts(_mapping(entry, path), path, unknowns)
    if not tensors:
        unknowns.append("header.tensors: empty; an empty header passes every join")

    stored = {}
    for index, row in enumerate(_list(inventory.get("tensors"), "inventory.tensors")):
        path = f"inventory.tensors[{index}]"
        row = _mapping(row, path)
        name = _text(row, "name", path, unknowns)
        if name is None:
            continue
        copies = _count(row.get("copies", 1), f"{path}.copies", 1)
        elements, size = _tensor_counts(row, path, unknowns, copies)
        entry = stored.setdefault(name, {"elements": [], "bytes": [], "buffer": True})
        entry["elements"].append(elements)
        entry["bytes"].append(size)
        entry["buffer"] = entry["buffer"] and row.get("buffer") is True

    claimed, matched, absent = set(), [], []
    multiply_claimed = set()
    for name in sorted(stored):
        entry = stored[name]
        selection = [key for key in tensors if _selects(name, key)]
        if not selection:
            if not entry["buffer"]:
                absent.append(name)
            continue
        multiply_claimed.update(claimed.intersection(selection))
        claimed.update(selection)
        entry["matched"] = True
        header_elements = _sum_known(tensors[key][0] for key in selection)
        header_bytes = _sum_known(tensors[key][1] for key in selection)
        inventory_elements = _sum_known(entry["elements"])
        inventory_bytes = _sum_known(entry["bytes"])
        matched.append({
            "name": name,
            "header_tensors": len(selection),
            "header_elements": header_elements,
            "inventory_elements": inventory_elements,
            "element_diff": header_elements - inventory_elements
            if header_elements is not None and inventory_elements is not None else None,
            "header_bytes": header_bytes,
            "inventory_bytes": inventory_bytes,
            "byte_diff": header_bytes - inventory_bytes
            if header_bytes is not None and inventory_bytes is not None else None,
        })
    unclaimed = sorted(name for name in tensors if name not in claimed)
    mismatched = [row["name"] for row in matched if row["element_diff"] or row["byte_diff"]]
    header_total = _sum_known(size for _, size in tensors.values())
    # A buffer computed at load may be absent from the file; count it only when stored there.
    inventory_total = _sum_known(
        size for entry in stored.values() if not entry["buffer"] or entry.get("matched")
        for size in entry["bytes"]
    )
    clean = not (unknowns or unclaimed or absent or mismatched or multiply_claimed)
    return {
        "analysis_status": "INSUFFICIENT_EVIDENCE" if unknowns else "COMPUTED",
        "join_clean": clean,
        "unclaimed_header_tensors": unclaimed,
        "multiply_claimed_header_tensors": sorted(multiply_claimed),
        "absent_stored_names": absent,
        "mismatched_names": mismatched,
        "matched": matched,
        "byte_checksum": {
            "header_bytes": header_total,
            "inventory_bytes": inventory_total,
            "equal": header_total == inventory_total
            if header_total is not None and inventory_total is not None else None,
        },
        "unknowns": unknowns,
        "limits": [
            "The join anchors stored weights only; it says nothing about KV growth, "
            "cache boundedness or per-rank placement.",
            "Equal byte totals do not imply a correct join: two swapped submodules "
            "with the same total pass the checksum.",
            "No layout is read; a clean join certifies nothing about per-rank bytes.",
        ],
    }


def kv_cache_bytes(layers, context_tokens):
    """Stored KV bytes per sequence at `context_tokens`, by each layer group's growth law.

    Each group is {name, layers, bytes_per_position, law, window|ratio|state_bytes}:
    `global` stores every position, `window` stores min(window, s), `compressed`
    stores ceil(s / ratio), `complete_groups` stores floor(s / ratio)
    and `constant` stores a fixed recurrent state. The
    result also reports which groups stay bounded as the context grows.
    """
    layers = _list(_copy_json(layers), "layers")
    context = _count(context_tokens, "context_tokens")
    unknowns, groups = [], []
    if not layers:
        unknowns.append("layers: empty")
    for index, group in enumerate(layers):
        path = f"layers[{index}]"
        group = _mapping(group, path)
        name = _text(group, "name", path, unknowns)
        count = _required_count(group, "layers", path, unknowns)
        law = group.get("law")
        if law not in KV_LAWS:
            unknowns.append(f"{path}.law: requires one of {'/'.join(KV_LAWS)}")
            continue
        _source(group.get("source"), f"{path}.source", unknowns, SOURCE_KINDS)
        if law == "constant":
            if group.get("state_bytes") is None:
                unknowns.append(f"{path}.state_bytes: missing")
                continue
            per_layer = _nonnegative(group.get("state_bytes"), f"{path}.state_bytes")
            positions, bounded = None, True
        else:
            width = _positive(group.get("bytes_per_position"), f"{path}.bytes_per_position")
            if width is None:
                unknowns.append(f"{path}.bytes_per_position: missing")
                continue
            if law == "global":
                positions, bounded = context, False
            elif law == "window":
                window = _required_count(group, "window", path, unknowns)
                if window is None:
                    continue
                positions, bounded = min(window, context), True
            else:
                ratio = _required_count(group, "ratio", path, unknowns)
                if ratio is None:
                    continue
                positions = context // ratio if law == "complete_groups" else -(-context // ratio)
                bounded = False
            per_layer = _scaled(width, positions, "KV bytes")
        if count is None:
            continue
        groups.append({
            "name": name,
            "law": law,
            "layers": count,
            "positions": positions,
            "bytes": _scaled(per_layer, count, "KV bytes"),
            "bounded_as_context_grows": bounded,
        })
    total = _finite(sum(group["bytes"] for group in groups), "KV bytes") if not unknowns else None
    return {
        "analysis_status": "INSUFFICIENT_EVIDENCE" if unknowns else "COMPUTED",
        "context_tokens": context,
        "groups": groups,
        "total_bytes": total,
        "bounded_as_context_grows": all(group["bounded_as_context_grows"] for group in groups)
        if groups and not unknowns else None,
        "unknowns": unknowns,
        "limits": [
            "Per sequence and per supplied bytes_per_position; batch, paging granularity "
            "and per-rank head splits are the caller's to apply.",
            "A layer declared global whose real attention is windowed overstates KV; "
            "one declared windowed but wired dense understates it. Check the wiring.",
        ],
    }


def _floor(op, key, path, unknowns):
    if op.get(key) is None:
        return None
    floor = _mapping(op.get(key), f"{path}.{key}")
    value = _nonnegative(floor.get("value"), f"{path}.{key}.value")
    _source(floor.get("source"), f"{path}.{key}.source", unknowns, FLOOR_KINDS)
    return value


def _rates(hardware, unknowns):
    rates, kinds = {}, set()
    for name, fact in _mapping(hardware.get("rates"), "hardware.rates").items():
        path = f"hardware.rates.{name}"
        fact = _mapping(fact, path)
        resource = fact.get("resource")
        if type(resource) is not str or resource not in RATE_UNITS:
            unknowns.append(f"{path}.resource: requires one of {'/'.join(RATE_UNITS)}")
            continue
        if fact.get("unit") != RATE_UNITS[resource]:
            unknowns.append(f"{path}.unit: requires {RATE_UNITS[resource]}; no implicit conversion")
        kind = _source(fact.get("source"), f"{path}.source", unknowns, RATE_KINDS)
        kinds.add(kind)
        if kind == "peak":
            _text(fact, "clock_basis", path, unknowns)
        value = _positive(fact.get("value"), f"{path}.value")
        if value is None:
            unknowns.append(f"{path}.value: {fact.get('missing_reason') or 'missing'}")
        rates[name] = (resource, value)
    if not rates:
        unknowns.append("hardware.rates: empty")
    basis = kinds.pop() if len(kinds) == 1 else None
    basis = basis if basis in RATE_KINDS else None
    if basis not in RATE_KINDS:
        unknowns.append("hardware.rates: requires all peak or all synthetic or all datasheet "
                        "sources; observed envelopes require separate calibration")
    return rates, basis


def phase_floors(phase, hardware):
    """Per-rank floors for one phase step from supplied per-op demands and peak rates.

    `phase.ops` lists {name, repeat, demand, bound_demand, link_latency_s,
    launch_floor_s, source}. `demand` maps a rate in `hardware.rates` to the
    amount the op actually moves or computes, in the unit that rate's resource
    consumes; an optional `bound_demand` holds the irreducible amount for the
    bound, never more than `demand`. Within an op, the maximum assumes full
    compute/memory overlap. Sequential link phases add up with the link latency;
    a launch floor is one more alternative time. These floors enter only the serial
    estimate, never the bound. Returns the resource-total bound and the serial
    per-op estimate separately. Datasheet rates populate a specification
    reference time and leave the hardware-qualified bound unavailable.
    """
    phase = _mapping(_copy_json(phase), "phase")
    hardware = _mapping(_copy_json(hardware), "hardware")
    unknowns = []
    kind = phase.get("phase")
    if kind not in PHASES:
        unknowns.append(f"phase.phase: requires one of {'/'.join(PHASES)}")
    for key in ("model_id", "layout", "hardware_id"):
        _text(phase, key, "phase", unknowns)
    if _text(hardware, "hardware_id", "hardware", unknowns) != phase.get("hardware_id"):
        unknowns.append("hardware.hardware_id: differs from phase")
    tokens = _positive(phase.get("tokens_per_step"), "phase.tokens_per_step")
    if tokens is None:
        unknowns.append("phase.tokens_per_step: missing")
    rates, basis = _rates(hardware, unknowns)
    assumptions = _assumptions(phase, "phase", unknowns)
    assumptions += _assumptions(hardware, "hardware", unknowns)

    totals = {name: 0.0 for name in rates}
    actual = {name: 0.0 for name in rates}
    ops = []
    for index, op in enumerate(_list(phase.get("ops"), "phase.ops")):
        path = f"phase.ops[{index}]"
        op = _mapping(op, path)
        name = _text(op, "name", path, unknowns)
        repeat = _count(op.get("repeat", 1), f"{path}.repeat", 1)
        _source(op.get("source"), f"{path}.source", unknowns, SOURCE_KINDS)
        demand = _mapping(op.get("demand"), f"{path}.demand")
        latency = _floor(op, "link_latency_s", path, unknowns)
        launch = _floor(op, "launch_floor_s", path, unknowns)
        if not demand and latency is None and launch is None:
            unknowns.append(f"{path}.demand: empty")
        amounts = {}
        for rate_name, amount in demand.items():
            amount = _nonnegative(amount, f"{path}.demand.{rate_name}")
            if rate_name not in rates:
                unknowns.append(f"{path}.demand.{rate_name}: no matching hardware rate")
                continue
            amounts[rate_name] = amount
            actual[rate_name] = _finite(
                actual[rate_name] + _scaled(amount, repeat, "actual resource demand"),
                "actual resource total",
            )
        floor = dict(amounts)
        for rate_name, amount in _mapping(op.get("bound_demand"), f"{path}.bound_demand").items():
            amount = _nonnegative(amount, f"{path}.bound_demand.{rate_name}")
            if rate_name not in amounts:
                unknowns.append(f"{path}.bound_demand.{rate_name}: not in demand")
            elif amount > amounts[rate_name]:
                unknowns.append(f"{path}.bound_demand.{rate_name}: exceeds demand")
            else:
                floor[rate_name] = amount
        for rate_name, amount in floor.items():
            totals[rate_name] = _finite(
                totals[rate_name] + _scaled(amount, repeat, "bound resource demand"),
                "bound resource total",
            )
        ops.append({"name": name, "repeat": repeat, "amounts": amounts,
                    "latency": latency, "launch": launch})
    if not ops:
        unknowns.append("phase.ops: empty")

    bound = binding = estimate = None
    datasheet_time = datasheet_binding = None
    per_op = []
    if not unknowns:
        times = {name: _finite(totals[name] / rates[name][1], "resource time") for name in rates}
        resource_time = max(times.values())
        limiting = sorted(name for name, value in times.items() if value == resource_time)
        if basis == "datasheet":
            datasheet_time, datasheet_binding = resource_time, limiting
        else:
            bound, binding = resource_time, limiting
        estimate = 0.0
        for op in ops:
            terms, links = {}, []
            link_time = 0.0
            for key, value in op["amounts"].items():
                if rates[key][0] == "link":
                    links.append(key)
                    link_time += value / rates[key][1]
                else:
                    terms[(key,)] = value / rates[key][1]
            if links or op["latency"] is not None:
                label = tuple(sorted(links)) or ("link_latency",)
                terms[label] = link_time + (op["latency"] or 0.0)
            if op["launch"] is not None:
                terms[("launch_floor",)] = op["launch"]
            op_time = max(terms.values()) if terms else 0.0
            estimate += _scaled(op_time, op["repeat"], "op time")
            per_op.append({
                "name": op["name"],
                "repeat": op["repeat"],
                "time_s": op_time,
                "binding": sorted(key for label, value in terms.items() if value == op_time
                                  for key in label),
            })
        estimate = _finite(estimate, "serial estimate")
    return {
        "analysis_status": "INSUFFICIENT_EVIDENCE" if unknowns else "COMPUTED",
        "evidence_basis": basis,
        "phase": kind,
        "tokens_per_step": tokens,
        "resource_totals": totals,
        "actual_resource_totals": actual,
        "conditional_bound_s": bound,
        "binding_resources": binding,
        "datasheet_resource_time_s": datasheet_time,
        "datasheet_binding_resources": datasheet_binding,
        "serial_estimate_s": estimate,
        "per_op": per_op,
        "tokens_per_s_at_bound": _finite(tokens / bound, "bound throughput") if bound else None,
        "tokens_per_s_at_serial_estimate": _finite(tokens / estimate, "serial throughput")
        if estimate else None,
        "assumptions": assumptions,
        "unknowns": unknowns,
        "inputs": {"phase": phase, "hardware": hardware},
        "limits": [
            "conditional_bound_s is a lower bound only if every demand is irreducible "
            "for the permitted variants and every rate is a peak at the clock the device "
            "actually runs that work at; it may reject a result.",
            "serial_estimate_s assumes full compute/memory overlap within each op and "
            "no overlap between ops. It includes any link latencies and launch floors "
            "and may only "
            "flag a faster result, never reject it.",
            "Per rank and per supplied counts; queueing, launch, synchronization and "
            "load imbalance are not modeled.",
            "No achievable utilization, speedup, quality, goal acceptance or E2E claim follows.",
        ],
    }
