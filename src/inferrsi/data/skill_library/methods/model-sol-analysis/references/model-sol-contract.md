# `model_sol.py` contract

The helper is pure arithmetic over supplied JSON. It reads no files, fetches
nothing, runs no device and grants no acceptance. Each function copies its
inputs, returns JSON-serializable data and leaves its inputs unchanged.

Every result carries `analysis_status`: `COMPUTED`, or `INSUFFICIENT_EVIDENCE`
when evidence is missing or incompatible. Missing evidence is listed in
`unknowns`, and no unit is converted implicitly. The only default is an op's
`repeat` and a stored tensor's `copies`, both 1 when absent. Malformed data, such
as non-JSON values, counts below their minimum, non-finite numbers or non-text
keys, raises `ValueError`. Neither status is a campaign verdict.

A `source` object is `{kind, locator}`. The allowed kinds depend on the field:

| Field | Allowed `kind` |
|---|---|
| checkpoint header | `measured` (read from the file) or `synthetic` |
| inventory, op demand, KV layer group | `derived`, `measured` or `synthetic` |
| hardware rate | `peak` or `synthetic`; all rates in one call must share one kind |
| link latency, launch floor | `measured`, `assumed` or `synthetic` |

A `peak` rate also needs `clock_basis`: the clock the device actually runs that
work at, and where that comes from. A spec sheet computed at a lower clock than
the part sustains understates the peak, and a bound built on it can reject a
real result.

## `join_checkpoint(header, inventory)`

Inputs:

- `header.tensors`: a map from verbatim header names to `{dtype, shape}`,
  merged across shards. `__metadata__` is ignored. `dtype` uses safetensors codes
  (`BF16`, `F8_E4M3`, `I32`, …); a packed format is priced at its container's
  width.
- `inventory.tensors`: a list of `{name, dtype, shape, copies, buffer}`.
  - A name segment `X` matches any all-digit segment, and the number of
    segments must agree.
  - Rows sharing a name are summed.
  - `copies` counts stored tensors sharing that name; the default is 1.
  - `buffer: true` marks a tensor computed at load, which may be absent from the
    file.

Outputs:

- `unclaimed_header_tensors`: header tensors that no stored name selects.
- `absent_stored_names`: non-buffer stored names that select nothing.
- `matched`: per stored name, the header and inventory physical elements and
  bytes, and their differences.
- `mismatched_names`: names whose element count or byte count differs.
- `byte_checksum`: header bytes against inventory bytes. Buffers count only when
  the header stores them.
- `join_clean`: true only when the status is `COMPUTED`, both residuals are
  empty and nothing mismatches.

The join is the gate; the byte checksum is only a checksum. Equal totals with a
non-clean join are expected when two submodules swap widths.

## `kv_cache_bytes(layers, context_tokens)`

Each layer group is `{name, layers, law, source, …}`. A missing `layers`,
`bytes_per_position`, `window`, `ratio` or `state_bytes` is an unknown.

| `law` | Stored positions | Extra fields | Bounded as context grows |
|---|---|---|---|
| `global` | `s` | `bytes_per_position` | no |
| `window` | `min(window, s)` | `bytes_per_position`, `window` | yes |
| `compressed` | `ceil(s / ratio)` | `bytes_per_position`, `ratio` | no |
| `constant` | fixed state | `state_bytes` | yes |

Outputs: per-group positions and bytes, `total_bytes` per sequence, and
`bounded_as_context_grows`, which is true only if every group is bounded.
Results are per sequence. Batch, paging granularity and per-rank head splits are
the caller's to apply, through `bytes_per_position` or a later multiplication.

## `phase_floors(phase, hardware)`

Inputs:

- `phase`: `{phase, model_id, layout, hardware_id, tokens_per_step, assumptions,
  ops}`, where `phase` is `prefill` or `decode`. `tokens_per_step` is a positive
  number and may be fractional, for example effective tokens per step under
  speculation.
- Each op: `{name, repeat, demand, bound_demand, link_latency_s,
  launch_floor_s, source}`.
  - `demand` maps a rate name to the per-rank amount the op actually moves or
    computes, in FLOP for a compute rate and in bytes for a memory or link rate.
    The helper cannot check that unit; the amount's source must state it.
  - `bound_demand` optionally replaces some of those amounts in the bound with
    the irreducible amount, for example the bytes of the cheapest collective
    algorithm the framework and fabric admit. Each key must appear in `demand`,
    and each amount must not exceed it; otherwise it is an unknown.
  - Link amounts within one op add up: model one op per collective, with each
    of its phases as a demand on the link that phase crosses.
  - `link_latency_s` is `{value, source}` in seconds. It is the whole latency of
    one instance of the op, already hops × per-hop latency summed over its
    phases, and it adds once to the op's summed link time. With no link demand,
    the latency alone is the op's link time.
  - `launch_floor_s` is `{value, source}` in seconds, one more alternative time
    for the op, not added to anything.
  - An op may carry only a latency or a launch floor.
- `hardware`: `{hardware_id, assumptions, rates}`. Each rate is
  `{resource, unit, value, source, clock_basis}`, where `resource` is `compute`
  (`FLOP/s`), `memory` (`byte/s`) or `link` (`byte/s`). Units must match
  exactly.

Outputs:

- `evidence_basis`: `peak` or `synthetic` when all rates share that kind, else
  null.
- `phase` and `tokens_per_step`: echoed from the input.
- `resource_totals`: per rate, the sum of the bound's amounts × `repeat`
  (`bound_demand` where given, else `demand`).
- `actual_resource_totals`: per rate, the sum of `demand × repeat`.
- `conditional_bound_s`: `max over rates (total / rate)`, with
  `binding_resources` naming the rates that reach it. Latencies and launch
  floors never enter it. It is a lower bound only if every demand is
  irreducible for the permitted variants and every rate is a peak at the clock
  the device actually runs that work at. It is the only figure that may reject a
  result.
- `serial_estimate_s`:
  `Σ_op repeat × max(compute and memory times, summed link time + latency, launch floor)`,
  from `demand`.
  It assumes no overlap between ops, so it can only flag a faster result, never
  reject one. It is never below the bound.
- `per_op`: each op's time and binding term: rate names (all of an op's link
  rates when the link term binds), `link_latency` or `launch_floor`.
- `tokens_per_s_at_bound` and `tokens_per_s_at_serial_estimate`:
  `tokens_per_step` over each time.
- `assumptions`, `unknowns`, a copy of the `inputs`, and `limits`.

The helper composes supplied per-rank counts only. Deriving the counts — fusion,
sharding, ring factors, hops, MoE load factors and KV growth — is the procedure's
job and is recorded with the counts' sources. It does not model queueing,
launches beyond supplied floors, synchronization or load imbalance beyond the
supplied counts. No achievable utilization, speedup, quality, goal acceptance or
end-to-end claim follows from its output.
