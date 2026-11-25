---
name: model-sol-analysis
description: Walk a whole model to per-phase (prefill, decode) speed-of-light figures under a declared parallel layout - anchored counts, the fused graph the framework runs, per-rank geometry, explicit communication and KV growth laws - and report a resource-total bound apart from a serial per-op estimate.
metadata:
  inferrsi: |
    {
      "schema_version": 1,
      "profile": "local-skill-v1",
      "kind": "skill",
      "status": "candidate",
      "origin": [
        "external"
      ],
      "empirical_validation": "not_run",
      "tags": [
        "performance",
        "roofline",
        "speed-of-light",
        "parallelism",
        "kv-cache",
        "inference"
      ],
      "sources": [
        {
          "type": "git",
          "url": "https://github.com/shenh10/HuggingArch",
          "commit": "e69d20a028e5b17524aa48b53bddf8b9aad5d15b",
          "revision_precision": "full",
          "license": "MIT",
          "observed_at": "2026-11-10",
          "paths": [
            "docs/inference_cost_model.md",
            "docs/evaluation_model.md",
            "docs/symbolic_evaluation.md",
            "docs/design.md",
            "docs/parallelism.md",
            "docs/kv_cache_storage.md",
            "docs/attention_families.md",
            "docs/moe_expert_axis.md",
            "docs/quantization.md",
            "docs/validation.md",
            "docs/measured_calibration.md",
            "docs/known_limitations.md",
            "README.md",
            "backend/inference/row_roofline.py",
            "backend/inference/phases.py",
            "backend/inference/phase_formulas.py",
            "backend/arch/eval/binding.py",
            "backend/arch/eval/transforms.py",
            "backend/arch/eval/fusion.py",
            "backend/inference/framework_bindings/__init__.py",
            "backend/arch/layout/weight_endpoints.py",
            "backend/arch/layout/layout.py",
            "backend/arch/layout/workload.py",
            "backend/arch/layout/physical.py",
            "backend/arch/layout/comm_volume.py",
            "backend/inference/comm_cost.py",
            "backend/arch/eval/cache.py",
            "backend/arch/eval/formats.py",
            "backend/arch/dtypes.py",
            "backend/arch/validate/_axioms.py",
            "backend/arch/validate/_orchestrator.py",
            "backend/arch/validate/_type_contracts.py",
            "backend/inference/sol_closure.py",
            "backend/inference/op_calibration.py",
            "backend/inference/calibration_overlay.py",
            "backend/measure/lookup.py"
          ],
          "identity": "references/huggingarch-source-identity.json",
          "readset": "references/huggingarch-model-sol.md",
          "note": "Cited paths only; the identity file records every retrieved file, its digests and its inspection scope, including files read but not cited. performance-ceiling-analysis keeps its own earlier pin for the checkpoint anchor."
        }
      ],
      "applicability": {
        "scope": "Model-level prefill and decode speed-of-light analysis for decoder-only (optionally multimodal) inference under a declared parallel layout; extends performance-ceiling-analysis L1 from one operation to a whole model without replacing its evidence rules",
        "hardware": "any; per-dtype peaks, memory bandwidth and link bandwidths must be supplied with sources",
        "prerequisites": "Model config and forward source at a pinned revision, the checkpoint's tensor headers where a checkpoint exists, the serving framework release that will run, and the layout and workload; reading the skill does not authorize execution",
        "input_contract": "Model config, forward source and checkpoint headers; serving framework and release with source anchors for every fusion; per-world parallel degrees, ranks per node and node count; batch, input, output, prefix and verify tokens, and the measured expert load skew when expert placement makes per-rank work depend on routing; per-dtype compute peaks at the sustained clock, memory and link bandwidths with sources; any launch floor or link latency labelled as an assumption",
        "produced_artifact": "A per-phase table with per-op counts and binding resource, per-resource totals, the conditional bound and its binding resources, the serial per-op estimate, headline TTFT, TPOT and throughput figures each labelled bound or estimate, every anchor and gate result, assumptions and unknowns; analytical only, not a measured result",
        "failure_modes": [
          "The serial per-op sum is reported as a bound, or used to reject a faster measurement",
          "Counts come from the unfused graph, overstating launches and activation round-trips, or from fusions the framework does not run, understating bytes",
          "A degree that does not divide a weight is silently replaced by a divisor that does",
          "Expert load skew is left at its default, making routed time and exchange optimistic",
          "A windowed layer is priced as global, or a dense layer as windowed, because the cache growth law was not checked",
          "Prefill attention is counted as a full square rather than causal pairs",
          "An unmeasured launch floor or link latency, or a spec-sheet peak below the sustained clock, enters the bound",
          "A measured envelope replaces the analytical figure instead of sitting beside it"
        ],
        "refusal_point": "Stops when an anchor gate fails or cannot be judged, when a required peak, used fabric rate or required expert-parallel load skew is missing, or when weights plus one request's KV do not fit a rank. Unanchored fusion permits only a labelled unfused estimate when its counts are available."
      },
      "recommendations": [
        "Anchor weights, shapes and KV growth before pricing any count, and treat an unjudged gate as a failure.",
        "Price the post-fusion graph the serving framework runs at its pinned release, with a source anchor for every fusion.",
        "Report the resource-total bound and the serial per-op estimate in separate columns; only the bound may reject a result.",
        "Keep unmeasured launch floors and link latencies out of the bound, as labelled assumptions in the estimate.",
        "Keep measured kernel times beside the analytical figure, joined by physical identity rather than model or framework name."
      ],
      "verification": {
        "locally_verified": false,
        "evidence_level": "source_grounded",
        "note": "Derived from a reviewed external implementation at a pinned commit (references/huggingarch-model-sol.md, identity in references/huggingarch-source-identity.json); claims read from executable code and claims stated only in the project's prose, docstrings included, are marked separately there. The bundled pure helper composes supplied counts only and is covered by synthetic tests; no accelerator, model or source-project run was used, and no predicted figure has been compared with a measurement."
      },
      "limitations": [
        "Source-derived candidate; no local efficacy validation.",
        "The serial estimate assumes full compute/memory overlap within an op, no overlap between ops and no pipeline bubble. The source uses one link latency for every fabric.",
        "Counts are only as good as the anchors and the framework binding behind them; behaviour that lives only in weights or custom runtime code is out of reach.",
        "Decoder-only models, optionally multimodal; encoder-decoder models are out of scope."
      ],
      "provenance_readsets": [
        "references/huggingarch-model-sol.md",
        "references/huggingarch-source-identity.json",
        "references/model-sol-contract.md",
        "references/model-sol-example.json",
        "references/qwen38-h200-tp4.md",
        "references/qwen38-h200-tp4.json"
      ],
      "consumption_mode": "packaged"
    }
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
  [weight-loading-optimization](../../optimization/weight-loading-optimization/SKILL.md).

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
  tokens. For expert parallelism, supply measured load skew `ρ` to price the
  busiest rank. For pure TP with identically routed expert shards, price the
  same selected tokens on every rank and state the distinct-expert assumption.
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

   Use `global` for full-context MHA, GQA, MQA and MLA when they retain one
   entry per position. Use the stored KV head widths for MHA/GQA/MQA and the
   stored latent plus any retained positional-key bytes for MLA. Use `window`
   for a proven fixed sliding window, `compressed` for a proven
   `ceil(context / ratio)` stored-position law, `complete_groups` for a full
   row only after each group closes (account for the tail separately), and `constant` for proven
   fixed-size recurrent state. Split hybrid layers by state component. Other
   layouts and cache growth laws require separate evidence.

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
  needs a source anchor (`path:line` at that release) and evidence it applies to
  the declared device and layout. When patterns overlap, resolve them by a
  fixed, stated order.
- Derive traffic from the fused graph's boundaries. A fused kernel's traffic is
  not the sum of its members' traffic.
- Know both failure directions. An unfused walk overstates launches and
  activation round-trips. Fusion the framework does not actually run
  understates bytes.
- Use the minimum evidenced demand for each resource across the admissible
  variants of the declared layout. If an unresolved fusion could reduce that
  demand, mark the affected bound `INSUFFICIENT_EVIDENCE`. An unfused graph
  with known counts can still provide a labelled serial estimate.
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
- A transfer needs an evidenced topology and finite positive bandwidth for
  each fabric that carries bytes. An unavailable rate on such a fabric yields
  `INSUFFICIENT_EVIDENCE`. Omit the transfer
  only when the layout establishes no transfer, for example a one-rank world.
- The latency term and any launch floor go into the serial estimate only,
  never into the bound. Label them as assumptions unless they were measured.

### 6. Compose the phase

Use `phase_floors` in the helper, or apply the same arithmetic by hand:

- **Conditional bound.** For each resource, total per-rank irreducible demand
  over its peak rate; take the maximum across resources. This is a lower bound
  only when the counts cannot be reduced by any permitted variant, such as a
  collective algorithm moving fewer bytes, and every rate is a peak at the clock
  the device actually runs that work at. Only a qualified peak-based bound may
  reject a result for that layout.
- **Serial estimate.**
  `Σ_op max(t_compute, t_memory, Σ_phases t_link + hops × latency, launch floor)`,
  with the counts the framework actually runs. The maximum assumes full
  compute/memory overlap within each op, and the sum assumes no overlap between
  ops. The phases of one collective run one after another, so their link times add. A
  stack that overlaps kernels or hides communication under compute can finish
  below it, so it can only flag a faster result. It can never reject one.
- Record the counts the selected graph actually runs in `demand`. For a phase
  bound, explicitly supply `bound_demand` for every positive demand and cite
  why that amount is unavoidable for the layout. A missing proof leaves the
  affected resource total and phase bound unknown. The scheduled counts still
  support a serial estimate. Use one op per collective, with each link phase
  assigned to the link it crosses.
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
- A fusion lacks a source anchor: report an unfused serial estimate if its
  counts are known. Withhold the bound if the unresolved fusion could reduce
  its demand.
- A per-dtype peak, a used link bandwidth or a required expert-parallel skew `ρ` is missing:
  the result is `INSUFFICIENT_EVIDENCE`, not a default.
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

For rates taken from a hardware datasheet, use `source.kind = "datasheet"`.
The reference time prices the specified workload at those nominal rates.
The qualified bound stays unavailable until the actual clock basis is known.
The [Qwen3.8-Flash-Next H200 TP4 worked example](references/qwen38-h200-tp4.md)
includes an offline replay and an optional public checkpoint-header audit.

## Resource contract

[`references/huggingarch-model-sol.md`](references/huggingarch-model-sol.md)
records the source method with per-claim markers, and
[`references/huggingarch-source-identity.json`](references/huggingarch-source-identity.json)
records the pinned commit, per-file digests and inspection scope. The checkpoint
anchor and the two-threshold rule stay with `performance-ceiling-analysis`; this
owner links to them. Candidate guidance; no local measurement.
