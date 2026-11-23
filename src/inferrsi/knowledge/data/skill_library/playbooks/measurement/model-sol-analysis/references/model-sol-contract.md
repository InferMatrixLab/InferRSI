# `model_sol.py` contract

The helper is pure arithmetic over supplied JSON. It reads no files, fetches
nothing, runs no device and grants no acceptance. Each function copies its
inputs, returns JSON-serializable data and leaves its inputs unchanged.

Every result carries `analysis_status`: `COMPUTED`, or `INSUFFICIENT_EVIDENCE`
when evidence is missing or incompatible. Missing evidence is listed in
`unknowns`, and no unit is converted implicitly. The only default is an op's
`repeat` and a stored tensor's `copies`, both 1 when absent. Malformed data, such
as non-JSON values, counts below their minimum, non-finite numbers or non-text
keys, raises `ValueError`. Derived arithmetic outside the finite numeric range
also raises `ValueError`. Neither status is a campaign verdict.

A link bandwidth is an evidence input. A positive transfer with a missing or
unusable bandwidth yields `INSUFFICIENT_EVIDENCE`. The helper accepts a Python
NaN or infinity specifically in a link's numeric `value` and records it as
JSON null in the returned hardware snapshot. Other inputs retain the finite
JSON requirement.

A `source` object is `{kind, locator}`. The allowed kinds depend on the field:

| Field | Allowed `kind` |
|---|---|
| checkpoint header | `measured` (read from the file) or `synthetic` |
| inventory, op demand, KV layer group | `derived`, `measured` or `synthetic` |
| hardware rate | `peak`, `synthetic` or `datasheet`. All rates in one call must share one kind. |
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

Both inputs require an explicit `shape`. An empty shape `[]` declares a
scalar. An absent or null shape leaves the affected counts unavailable.

Outputs:

- `unclaimed_header_tensors`: header tensors that no stored name selects.
- `multiply_claimed_header_tensors`: header tensors selected by more than one
  distinct stored name.
- `absent_stored_names`: non-buffer stored names that select nothing.
- `matched`: per stored name, the header and inventory physical elements and
  bytes, and their differences.
- `mismatched_names`: names whose element count or byte count differs.
- `byte_checksum`: header bytes against inventory bytes. Buffers count only when
  the header stores them. An unknown size leaves the affected total and
  equality flag null.
- `join_clean`: true only when the status is `COMPUTED`, both residuals are
  empty, all matches agree and each header tensor is selected exactly once.

The join is the gate; the byte checksum is only a checksum. Equal totals with a
non-clean join are expected when two submodules swap widths.

## `kv_cache_bytes(layers, context_tokens)`

Each layer group is `{name, layers, law, source, …}`. An empty or absent list
of groups, or a missing required field for a group's law, is an unknown.

| `law` | Stored positions | Extra fields | Bounded as context grows |
|---|---|---|---|
| `global` | `s` | `bytes_per_position` | no |
| `window` | `min(window, s)` | `bytes_per_position`, `window` | yes |
| `compressed` | `ceil(s / ratio)` | `bytes_per_position`, `ratio` | no |
| `complete_groups` | `floor(s / ratio)` | `bytes_per_position`, `ratio`. Account for any open-group buffer separately. | no |
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
  - `bound_demand` declares counts known to be irreducible across the permitted
    variants of this layout. Cite that evidence in the op's source, for example
    the minimum traffic across all admissible collective algorithms. Each key
    must occur in `demand`, with a value between zero and its scheduled amount.
    Supply an explicit zero when it is the evidenced minimum for positive work.
    An absent, empty or null map, an omitted key and a null value all leave
    irreducibility unknown for the corresponding positive demand. A scheduled
    count of zero already establishes a lower count of zero.
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
    exactly. Provide a valid rate for every fabric used by the declared
    layout and schedule. A missing, non-finite or nonpositive link bandwidth
    leaves timing and throughput unavailable for a positive transfer. A
    single-rank schedule with zero bytes on that link needs no bandwidth
    observation. The scheduled byte count is retained in both cases.

Outputs:

- `evidence_basis`: `peak`, `synthetic` or `datasheet` when all rates share that kind, else
  null.
- `phase` and `tokens_per_step`: echoed from the input.
- `resource_totals` gives the sum of the evidenced lower counts × `repeat`
  for each rate. A rate's total is null if any op using it lacks that evidence.
- `actual_resource_totals`: per rate, the sum of `demand × repeat`.
- `conditional_bound_s`: `max over rates (total / rate)`, with
  `binding_resources` naming the rates that reach it. Latencies and launch
  floors never enter it. It is a lower bound only if every demand is
  irreducible for the permitted variants of the declared layout and every rate
  is a peak at the clock the device actually runs that work at. Only a bound
  meeting those conditions may reject a result.
- If only irreducibility evidence is missing with `peak` or `synthetic` rates,
  the status is `INSUFFICIENT_EVIDENCE`. The phase bound, its binding resources
  and its throughput are null. The helper still reports the serial estimate,
  its throughput and per-op rows from the evidenced schedule. For example,
  400 scheduled bytes at 100 B/s give a 4 s serial estimate. Explicit evidence
  for 100 irreducible bytes adds a 1 s bound for that single-resource example.
- `datasheet_resource_time_s` and `datasheet_binding_resources` carry the
  resource-total calculation using `actual_resource_totals` at the vendor
  specifications. This calculation needs only the schedule. In that mode
  `conditional_bound_s`, `binding_resources`
  and `tokens_per_s_at_bound` are null. The serial estimate uses the same
  nominal rates. These reference times cannot reject an observation.
- `serial_estimate_s`:
  `Σ_op repeat × max(compute and memory times, summed link time + latency, launch floor)`,
  from `demand`.
  It assumes full compute/memory overlap within an op and no overlap between
  ops. It may flag a faster result. With the same counts and rate domains it
  is never below the resource-total bound.
- `per_op`: each op's time and binding term: rate names (all of an op's link
  rates when the link term binds), `link_latency` or `launch_floor`.
- `tokens_per_s_at_bound` and `tokens_per_s_at_serial_estimate`:
  `tokens_per_step` over each positive time, or null when the time is zero or
  unavailable.
- `assumptions`, `unknowns`, a copy of the `inputs`, and `limits`.

The helper composes supplied per-rank counts only. Deriving the counts — fusion,
sharding, ring factors, hops, MoE load factors and KV growth — is the procedure's
job and is recorded with the counts' sources. It does not model queueing,
launches beyond supplied floors, synchronization or load imbalance beyond the
supplied counts. No achievable utilization, speedup, quality, goal acceptance or
end-to-end claim follows from its output.
