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
KV_LAWS = ("global", "window", "compressed", "constant")
RATE_UNITS = {"compute": "FLOP/s", "memory": "byte/s", "link": "byte/s"}
SOURCE_KINDS = ("derived", "measured", "synthetic")
RATE_KINDS = ("peak", "synthetic")
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


def _elements(shape, path):
    shape = _list(shape, path)
    total = 1
    for index, size in enumerate(shape):
        total *= _count(size, f"{path}[{index}]")
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
    summed. Returns both residuals, per-name element and byte comparisons and the
    byte checksum. The join is the gate; the byte total is only its checksum.
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
        entry = _mapping(entry, f"header.tensors.{name}")
        width = DTYPE_BYTES.get(entry.get("dtype"))
        if width is None:
            unknowns.append(f"header.tensors.{name}.dtype: no known byte width")
        tensors[name] = (_elements(entry.get("shape"), f"header.tensors.{name}.shape"), width)
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
        width = DTYPE_BYTES.get(row.get("dtype"))
        if width is None:
            unknowns.append(f"{path}.dtype: no known byte width; bytes cannot be formed")
        entry = stored.setdefault(name, {"elements": 0, "bytes": 0, "buffer": True})
        elements = _elements(row.get("shape"), f"{path}.shape") * copies
        entry["elements"] += elements
        entry["bytes"] += elements * (width or 0)
        entry["buffer"] = entry["buffer"] and row.get("buffer") is True

    claimed, matched, absent = set(), [], []
    for name in sorted(stored):
        entry = stored[name]
        selection = [key for key in tensors if _selects(name, key)]
        if not selection:
            if not entry["buffer"]:
                absent.append(name)
            continue
        claimed.update(selection)
        entry["matched"] = True
        header_elements = sum(tensors[key][0] for key in selection)
        header_bytes = sum(tensors[key][0] * (tensors[key][1] or 0) for key in selection)
        matched.append({
            "name": name,
            "header_tensors": len(selection),
            "header_elements": header_elements,
            "inventory_elements": entry["elements"],
            "element_diff": header_elements - entry["elements"],
            "header_bytes": header_bytes,
            "inventory_bytes": entry["bytes"],
            "byte_diff": header_bytes - entry["bytes"],
        })
    unclaimed = sorted(name for name in tensors if name not in claimed)
    mismatched = [row["name"] for row in matched if row["element_diff"] or row["byte_diff"]]
    header_total = sum(elements * (width or 0) for elements, width in tensors.values())
    # A buffer computed at load may be absent from the file; count it only when stored there.
    inventory_total = sum(
        entry["bytes"] for entry in stored.values() if not entry["buffer"] or entry.get("matched")
    )
    clean = not unknowns and not unclaimed and not absent and not mismatched
    return {
        "analysis_status": "INSUFFICIENT_EVIDENCE" if unknowns else "COMPUTED",
        "join_clean": clean,
        "unclaimed_header_tensors": unclaimed,
        "absent_stored_names": absent,
        "mismatched_names": mismatched,
        "matched": matched,
        "byte_checksum": {
            "header_bytes": header_total,
            "inventory_bytes": inventory_total,
            "equal": header_total == inventory_total,
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
    stores ceil(s / ratio) and `constant` stores a fixed recurrent state. The
    result also reports which groups stay bounded as the context grows.
    """
    layers = _list(_copy_json(layers), "layers")
    context = _count(context_tokens, "context_tokens")
    unknowns, groups = [], []
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
                positions, bounded = -(-context // ratio), False
            per_layer = _finite(width * positions, "KV bytes")
        if count is None:
            continue
        groups.append({
            "name": name,
            "law": law,
            "layers": count,
            "positions": positions,
            "bytes": _finite(per_layer * count, "KV bytes"),
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
        if resource not in RATE_UNITS:
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
        unknowns.append("hardware.rates: requires all peak or all synthetic sources; "
                        "measured envelopes are conditional estimates, not bound inputs")
    return rates, basis


def phase_floors(phase, hardware):
    """Per-rank floors for one phase step from supplied per-op demands and peak rates.

    `phase.ops` lists {name, repeat, demand, bound_demand, link_latency_s,
    launch_floor_s, source}. `demand` maps a rate in `hardware.rates` to the
    amount the op actually moves or computes, in the unit that rate's resource
    consumes; an optional `bound_demand` holds the irreducible amount for the
    bound, never more than `demand`. Within an op, link times add up (sequential
    collective phases) and the link latency adds once; a launch floor is one more
    alternative time. Latencies and launch floors enter only the serial
    estimate, never the bound. Returns the resource-total bound and the serial
    per-op estimate separately.
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
            actual[rate_name] += amount * repeat
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
            totals[rate_name] += amount * repeat
        ops.append({"name": name, "repeat": repeat, "amounts": amounts,
                    "latency": latency, "launch": launch})
    if not ops:
        unknowns.append("phase.ops: empty")

    bound = binding = estimate = None
    per_op = []
    if not unknowns:
        times = {name: _finite(totals[name] / rates[name][1], "resource time") for name in rates}
        bound = max(times.values())
        binding = sorted(name for name, value in times.items() if value == bound)
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
            estimate += _finite(op_time * op["repeat"], "op time")
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
        "serial_estimate_s": estimate,
        "per_op": per_op,
        "tokens_per_s_at_bound": tokens / bound if bound else None,
        "tokens_per_s_at_serial_estimate": tokens / estimate if estimate else None,
        "assumptions": assumptions,
        "unknowns": unknowns,
        "inputs": {"phase": phase, "hardware": hardware},
        "limits": [
            "conditional_bound_s is a lower bound only if every demand is irreducible "
            "for the permitted variants and every rate is a peak at the clock the device "
            "actually runs that work at; it may reject a result.",
            "serial_estimate_s assumes no overlap between ops and includes any link "
            "latencies and launch floors; it is a conditional estimate and may only "
            "flag a faster result, never reject it.",
            "Per rank and per supplied counts; queueing, launch, synchronization and "
            "load imbalance are not modeled.",
            "No achievable utilization, speedup, quality, goal acceptance or E2E claim follows.",
        ],
    }
