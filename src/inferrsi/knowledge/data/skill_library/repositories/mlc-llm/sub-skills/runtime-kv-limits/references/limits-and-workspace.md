# Limit reconciliation and workspace provenance

Source: [config.cc](https://github.com/mlc-ai/mlc-llm/blob/8978ea9aec626d64096aaa92fbc89bda2e3ea802/cpp/serve/config.cc#L548-L815)
and selected [configuration declarations](https://github.com/mlc-ai/mlc-llm/blob/8978ea9aec626d64096aaa92fbc89bda2e3ea802/cpp/serve/config.h#L174-L203).
These are source contracts, not executed C++ or observed allocation results.

## Per-model clamp, then cross-model minimum

For context and prefill, `-1` is the inspected unspecified/unbounded sentinel.
If the compiled value is finite, runtime `-1` or a larger runtime value becomes
that compiled value; otherwise the runtime value is retained. Aggregates take
the minimum finite compiled/runtime values across models. Compiled maximum
batch and finite runtime sliding windows are also minima. No finite context
bound can remain the internal signed-64 maximum sentinel. This is not a promise
that unlimited context fits memory or that arbitrary sentinel arithmetic is safe.

The source explicitly requires finite positive compiled/runtime prefill and
aggregate batch. A model with an unspecified compiled prefill does not by itself
fail that aggregate assertion when another model supplies a finite minimum.
The helper's positive-or-`-1` domain is deliberately narrower than the complete
native JSON parser and is not a new upstream input policy.

## Engine inference branches are not interchangeable

In EstimateMemoryUsageOnMode, absent sequence count selects local at most four,
interactive one, or server compiled maximum. An explicitly supplied sequence
count is retained in this function. Absent single-sequence length comes from
runtime aggregate; an explicit one is capped by the compiled aggregate.

Workspace formulas read **nested `model_config.prefill_chunk_size`**. They do
not simply use a reduced runtime prefill. KV bytes-per-token, auxiliary space,
model workspace and logit-processor space are separate terms; temporary buffers
and parameter bytes come from metadata. These formulas contain source-specific
assumptions and are not a complete allocator/pressure model. A smaller runtime
prefill with unchanged compiled inputs does not prove reduced workspace.

The selected DeviceAPI memory attribute is scaled by utilization and reduced by
estimated parameters/workspaces before automatic capacity is chosen. Pinned
TVM's [Metal attribute](https://github.com/mlc-ai/relax/blob/201fa0001c81431ccce05419b442c47779ea917c/src/backend/metal/runtime/metal_device_api.mm#L65-L145)
uses `recommendedMaxWorkingSetSize`, not authenticated free RAM, free GPU memory
or an allocation receipt. Apple unified memory does not erase private buffers,
other processes, pending work or runtime overhead.

Metal caps the **estimated automatic** total-cache capacity at 32768; local
automatic selection also applies 8192. These are pinned implementation choices,
not universal safe capacities, tuning advice or acceptance thresholds. Explicit
`max_total_sequence_length` bypasses this automatic selection branch. Likewise,
local/interactive automatic prefill takes runtime/total/single minima, server
automatic prefill uses runtime aggregate, while explicit prefill is retained in
this function. Do not fabricate a global override rejection from these branches;
inspect the actual caller/validation path before asserting engine admission.

This slice covers KV mode, not full RNN-state estimation, scheduler admission,
concurrent prefix reuse or all configurations. The helper computes no capacity,
allocation size, effective engine config, latency, quality or physical fit.
