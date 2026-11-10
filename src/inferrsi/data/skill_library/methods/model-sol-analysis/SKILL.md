---
name: model-sol-analysis
description: Walk a whole model to per-phase (prefill, decode) speed-of-light figures under a declared parallel layout - anchored counts, the fused graph the framework runs, per-rank geometry, explicit communication and KV growth laws - and report a resource-total bound apart from a serial per-op estimate.
---

# Model-level speed-of-light analysis

Status: candidate; `empirical_validation: not_run`. Reading this skill does not
authorize execution; follow the current task's scope.

## When to use this skill

Use it to answer model-level ceiling questions before building or tuning
anything:

- What is the prefill and decode ceiling of model M under layout L on card H?
- Is a requested TTFT or TPOT physically plausible at this batch and context?
- Which resource binds decode at context length s, and does it move with s?
- How do two layouts compare analytically?

This skill extends [performance-ceiling-analysis](../performance-ceiling-analysis/SKILL.md).
That owner's L1 helper prices one device, one operation class and one traffic
tier, and its contract states that it does not walk a model, sum devices or
compose stages. This skill does the model walk and keeps that owner's evidence
rules.

Do not use it for:

- benchmarking built candidates: use `rsi-evidence` and the AB/BA harness;
- queueing, admission or percentile SLO prediction: use
  [calibrate-serving-simulation](../calibrate-serving-simulation/SKILL.md);
- one operation's roofline: use `performance-ceiling-analysis`;
- weight loading mechanics: use
  [weight-loading-optimization](../weight-loading-optimization/SKILL.md).

## Inputs

Gather these before any arithmetic. Mark a missing item unknown; do not borrow a
default from a paper or another card.

- **Model:** config and forward source at a pinned revision. Also the
  checkpoint's tensor headers, or an explicit statement that none exists.
- **Framework:** the serving framework and the release that will actually run.
  Its fusions and dispatch choices determine which graph is priced.
- **Layout:** per-world degrees (tensor, context, expert, pipeline, data), plus
  ranks per node and node count.
- **Workload:** batch; input, output and prefix tokens; speculative verify
  tokens; for MoE, the measured expert load skew `ρ`.
- **Hardware:** per-dtype dense compute peak, memory bandwidth, and intra- and
  inter-node link bandwidth, each with its source and the clock it assumes. Use
  the clock the device actually runs that work at: a spec sheet computed at a
  lower clock understates the peak, and a measured row will then beat the
  "bound". Record a launch floor or link latency only as a labelled assumption
  unless it was measured.

## Procedure

### 1. Anchor the counts before pricing them

A floor computed from wrong counts is wrong in a way no roofline step detects.
Pass every gate below, or stop and report which gate failed. A gate that could
not be judged counts as a failure.

1. **Weights.** Run the two gates in
   [checkpoint anchoring](../performance-ceiling-analysis/references/huggingarch-checkpoint-anchor.md):
   the bidirectional per-tensor join, then the per-rank weight ledger.
   `join_checkpoint` in the helper does the join and its byte checksum. A clean
   byte total alone is not a pass.
2. **Shapes.** Every op's input shapes must match what it declares, and every
   split or merged dimension must multiply back. A byte total that happens to
   match does not excuse a graph whose tensors do not compose.
3. **KV type.** Every attention component names its cache family. Every decode
   attention path either stores per-token entries or carries a recurrent state.
4. **KV growth.** For each cached tensor, state its storage law. Check it by
   letting the context grow without bound: a per-token tensor must grow, a
   windowed one must cap, and a constant state must not depend on the context. A
   window in the model config must show up as a capped tensor. `kv_cache_bytes`
   in the helper applies the laws.

### 2. Bind each phase before walking the graph

- **Prefill:** `s_query = input − prefix`, `s_kv = input`.
- **Decode:** `s_query` = verified tokens per step `k` (1 without
  speculation). `s_kv` = the cache length in question plus `k − 1`. If you use
  the average over the generation (`input + output/2`) as the cache length, say
  so: the time at the mean length is not the mean time when an op switches its
  binding resource along the way.
- **Attention work:** count causal pairs,
  `s_pairs = s_query·(s_kv − s_query) + s_query(s_query+1)/2`, not `s²`.
- **Serving form:** use each component's actual form for the phase, such as
  absorbed MLA at decode.

### 3. Price the graph the framework runs

- Apply the serving framework's fusions at its pinned release. Every fusion
  needs a source anchor (`path:line` at that release); without one, do not apply
  it. When patterns overlap, resolve them by a fixed, stated order.
- Derive traffic from the fused graph's boundaries. A fused kernel's traffic is
  not the sum of its members' traffic.
- Know both failure directions. An unfused walk overstates launches and
  activation round-trips. Fusion the framework does not actually run
  understates bytes.
- Model a dispatch condition only when it changes bytes or the main kernel path
  in common deployments. Otherwise bill the default path and state that
  assumption.

### 4. Evaluate per rank, from per-rank shapes

- Derive each rank's work from its own shapes, not from a divisor table. Data
  parallelism divides no work: the step time is per replica group.
- Declare, per stored axis, which parallel world splits each weight. For a
  degree that does not divide the part count, use the declared policy: refuse,
  let a group of ranks co-own each shard (`gcd(parts, degree)` ways), or pad to
  whole parts. Never substitute a divisor that divides. Price a padded rank at
  its padded width.
- **MoE:** expert parallelism distributes whole experts. The busiest rank
  receives `(ρ + (k−1)(E−ρ)/(E−1)) / k` times the mean routed rows, for `k` local
  experts out of `E`. This assumes one hot expert. Without a measured `ρ`, the
  routed time is optimistic: report it as unknown, not as `ρ = 1`.
- **Context parallelism:** state which scheme cuts query rows, which cuts keys,
  and whether it divides KV at all.
- **Precision:** take bytes from the stored format (packing and scale siblings
  included). Take compute from the MMA width the framework launches. These are
  two different widths.

### 5. Make communication explicit

- Insert a collective wherever the sharding state changes:
  - partial to full: all-reduce;
  - sharded to replicated: all-gather;
  - MoE shuffle: all-to-all;
  - pipeline cut: send/receive.
- **Bytes per rank and hops** depend on the algorithm the framework picks for
  the payload. Name it:

  | Algorithm | Hops | Bytes per rank (tensor `T`, `N` ranks) |
  |---|---|---|
  | Library default (ring bytes, log-depth hops) | `ceil(log2 N)`, doubled for all-reduce | `(N−1)/N·T`, doubled for all-reduce |
  | One-shot all-reduce | 1 | `(N−1)·T` |
  | Two-shot all-reduce | 2 | `2(N−1)/N·T` |
  | In-switch reduction (NVLink SHARP) | 2 | `(N−1)/N·T` |
  | Point-to-point | 1 | `T` |

  For the bound, use the fewest bytes among the algorithms the framework and
  fabric admit, since any of them could run.
- **Time:** bytes over the bandwidth of the link the collective crosses, plus
  hops × link latency. A node-spanning all-reduce can run hierarchically:
  intra-node reduce-scatter, inter-node all-reduce on the shard, intra-node
  all-gather. This needs more than one rank per node and a world that divides
  evenly by it. State which schedule you assume.
- The latency term and any launch floor go into the serial estimate only,
  never into the bound. Label them as assumptions unless they were measured.

### 6. Compose the phase

Use `phase_floors` in the helper, or apply the same arithmetic by hand:

- **Conditional bound.** For each resource, total per-rank irreducible demand
  over its peak rate; take the maximum across resources. This is a lower bound
  only when the counts cannot be reduced by any permitted variant, such as a
  collective algorithm moving fewer bytes, and every rate is a peak at the clock
  the device actually runs that work at. Only this figure may reject a result.
- **Serial estimate.**
  `Σ_op max(t_compute, t_memory, Σ_phases t_link + hops × latency, launch floor)`,
  with the counts the framework actually runs and no overlap between ops. The
  phases of one collective run one after another, so their link times add. A
  stack that overlaps kernels or hides communication under compute can finish
  below it, so it can only flag a faster result. It can never reject one.
- In the helper, `demand` carries the counts actually run, and an optional
  `bound_demand` carries the irreducible counts for the bound (never more than
  `demand`). One op per collective, with each of its link phases as a demand on
  the link it crosses.
- **Pipeline parallelism:** one microbatch's latency is the stages plus the
  inter-stage hops, with no bubble modelled. Say so.
- **Capacity first:** if weights plus one request's KV do not fit a rank,
  publish no time for that layout.

### 7. Report headline figures with their labels

- **TTFT:** the prefill step.
- **TPOT:** the decode step, divided by `1 + α·K` under speculation with
  acceptance `α` and `K` drafts. The decode step must then include the draft's
  forward passes.
- **Decode throughput:** effective tokens per step over the decode step. Under
  speculation this count is fractional.

Each figure carries its label (bound or estimate), its phase binding, its
layout and its unknowns.

### 8. Calibrate beside the model, never over it

- Join measured kernel times by physical identity: op signature, shapes, dtypes,
  device and phase. Do not join by model or framework name.
- Keep the analytical and measured columns side by side.
- Rescale a row measured under different peaks by the ratio for the resource it
  saturated. With no known peak, do not rescale.
- Apply the rules in [the two-threshold rule](../performance-ceiling-analysis/references/huggingarch-checkpoint-anchor.md#which-bound-may-reject-a-measurement-the-two-threshold-rule):
  - A row claiming more work per second than its own recorded peak contradicts
    itself. Correct its numerator or peak, then check it again.
  - A row faster than a separately computed roofline is flagged, and both sides
    are re-derived.
- If the collectives were not measured, a phase containing one has no complete
  measured total.

## Output

Produce a per-phase table with:

- per-op rows: counts, per-resource time and binding resource;
- per-resource totals;
- the conditional bound with its binding resource or resources;
- the serial estimate;
- headline figures;
- every anchor and gate result;
- assumptions and unknowns.

Keep the bound and the estimate in separate columns. Never print an unlabelled
"SOL".

## Failure and stop conditions

- An anchor gate fails or cannot be judged: stop and name the gate.
- A fusion lacks a source anchor: price the unfused form and state the
  direction of the error.
- A per-dtype peak, a link bandwidth or (for MoE) `ρ` is missing: the result is
  `INSUFFICIENT_EVIDENCE`, not a default.
- The serial estimate is called a bound, or used to reject a measurement:
  correct the label before reporting.
- Capacity fails for the layout: publish no time.
- A measured envelope is treated as a bound: it is evidence about one stack, not
  a physical limit.

## Known gaps

The source method does not model:

- inter-kernel overlap, multi-stream execution or the pipeline bubble;
- per-fabric link latencies;
- generic compiler fusion it cannot anchor;
- behaviour that lives only in weights or custom runtime code.

It covers decoder-only models, optionally multimodal. Details and markers are in
the [source reading](references/huggingarch-model-sol.md).

## Helper

[`scripts/model_sol.py`](scripts/model_sol.py) is pure: JSON in, JSON out, and
no I/O, network or device access. Its inputs, outputs and limits are in the
[helper contract](references/model-sol-contract.md), with a synthetic
[example](references/model-sol-example.json).

- `join_checkpoint(header, inventory)`: the bidirectional join, per-name
  element and byte comparison, and the byte checksum.
- `kv_cache_bytes(layers, context_tokens)`: stored KV per sequence by growth law,
  with boundedness as the context grows.
- `phase_floors(phase, hardware)`: the conditional bound, binding resources,
  serial estimate and per-op rows for one phase step.

Each function reports missing evidence as unknowns and returns
`INSUFFICIENT_EVIDENCE` rather than guessing. Malformed data raises
`ValueError`.

## Resource contract

[`references/huggingarch-model-sol.md`](references/huggingarch-model-sol.md)
records the source method with per-claim markers, and
[`references/huggingarch-source-identity.json`](references/huggingarch-source-identity.json)
records the pinned commit, per-file digests and inspection scope. The checkpoint
anchor and the two-threshold rule stay with `performance-ceiling-analysis`; this
owner links to them. Candidate guidance; no local measurement.
