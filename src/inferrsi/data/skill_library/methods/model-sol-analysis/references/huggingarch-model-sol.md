# HuggingArch: model-level speed-of-light method, source reading

Status: candidate; `empirical_validation: not_run`. This document records what one
external project does to turn a model, a layout and a card into per-phase
speed-of-light times, read at one pinned commit and recorded in
[`huggingarch-source-identity.json`](huggingarch-source-identity.json). The
procedure in [`SKILL.md`](../SKILL.md) is derived from it. Claims carry one of
two markers:

- `[code]` — verified in executable code (statements, constants, signatures) of
  a file inspected at that commit;
- `[doc]` — stated only in the project's own prose: its documentation, or a
  docstring or comment in an inspected source file. Where the behaviour lives in
  a file that was not inspected, the claim is `[doc]` even if a docstring in an
  inspected file describes it.

A parenthesised locator names the file, section or symbol behind the marker.
Documentation paths are under `docs/`, code paths under `backend/`. Where this
document interprets rather than reports, the text says so.

The checkpoint weight anchor from the same project is documented, at an earlier
pin, under [performance-ceiling-analysis](../../performance-ceiling-analysis/references/huggingarch-checkpoint-anchor.md).
It is not repeated here; the files it relied on are byte-identical at this pin
except `docs/measured_calibration.md` and `docs/parallelism.md` (see the
identity record).

## 1. What the source calls SOL

- Each fused leaf row takes the maximum of four alternative times: compute
  (FLOPs over the compute peak), memory (weight read, metadata and activation
  bytes over bandwidth), communication (bytes over link bandwidth plus a link
  latency) and a launch floor `[code]` (`inference/row_roofline.py`,
  `build_row_exprs`). That the compute peak is the one for the row's
  activation dtype is stated in the module docstring `[doc]`.
- A phase step is the serial sum of those rows `[code]` (`inference/phases.py`,
  `t_sol = step.total(...)`; `inference/phase_formulas.py`, `STEP_SOL_LAW`
  "Σ_leaf max(t_compute, t_memory, t_comm, t_launch)").
- The source states the assumption behind the sum: "Rows are serial: the step is
  the sum of its rows, and no compute hides a collective or another kernel's
  launch" `[doc]` (`inference_cost_model.md`, "The roofline: four bounds per op").
- It rejects the model-level form `max(Σ flops / peak, Σ bytes / bw)` as "the
  tempting shortcut" that "*under-counts* the true time", and states that the
  per-op sum lies between the largest component sum and the sum of all four
  `[doc]` (same file, "Why SOL is a per-op sum, not a model-level max").
- It calls the result "an upper bound — the *speed of light*, not a promised
  latency" and conditions that on the peak being a real bound: "the card's dense
  peak at the clock it actually runs tensor-core work at, not the clock a spec
  sheet is computed at" `[doc]` (same file, "Calibration: from peak to
  achievable"). The project describes its latency as "a planning envelope, not a
  benchmark" `[doc]` (`README.md`, Scope).

The source also states the other side of that trade. Next to the serial sum,
a code comment says the whole-step `max(F/Fp, B/Bp)` "assumes perfect overlap
across every kernel in the model, so it is a bound and not an estimate" `[doc]`
(`inference/phases.py`, `estimate_phase` comment). It publishes the per-op sum
as its SOL. The skill reports both: the resource-total maximum as the bound,
and the per-op sum, which a stack that overlaps kernels or hides a collective
under compute can beat, as a serial estimate.

## 2. Binding a phase before the walk

- Prefill binds `s_query = input − prefix` and `s_kv = input`. Decode binds
  `s_query` to the verified tokens per step `k`, and `s_kv` to a cache length
  plus `k − 1`. The cache length is the explicit one when given, otherwise the
  average over the generation, `input + output/2`; the `k − 1` applies to both
  `[code]` (`arch/eval/transforms.py`, `Phase.resolve`).
- Attention work is counted in exact causal pairs:
  `s_past = s_kv − s_query` and `s_pairs = s_query·s_past + s_query(s_query+1)/2`
  `[code]` (`arch/eval/binding.py`, `STEP_LAWS`).
- Each component's serving form for the phase, such as absorbed MLA at decode,
  is swapped in before the walk, because the absorbed form has a cost of its own
  `[doc]` (`inference_cost_model.md`, "Two phases: prefill and decode";
  `Phase.substitute` docstring).
- A phase without per-op rows raises instead of falling back, and a deployment
  without capacity publishes no time `[code]` (`inference/phases.py`,
  `estimate_phase`).
- Headline figures: TTFT is the prefill step; TPOT is the decode step divided by
  `1 + α·K` under speculation; decode throughput is effective tokens per step
  over the decode step `[doc]` (`inference_cost_model.md`, "From per-step time
  to the headline numbers").
- Under pipeline parallelism a step is one microbatch's latency: the stages in
  sequence plus the inter-stage handoff, with the fill/drain bubble not modelled
  `[doc]` (`inference/phases.py`, `estimate_phase` comments and note string). The
  summing itself happens in a part of the calibration overlay that was not
  inspected.

## 3. Which graph is priced

- The per-op sum is taken over the post-fusion leaves, and traffic is
  re-derived from the rewritten graph's boundaries rather than summed over the
  fused members `[doc]` (`inference_cost_model.md`, "Fusion: collapsing memory
  round-trips"; `evaluation_model.md`, Layers). The traffic derivation itself is
  in a file not inspected.
- Fusions come from a binding for the serving framework, not from a generic
  registry. Larger patterns are applied first, and overlapping matches resolve
  "first wins" `[code]` (`inference/framework_bindings/__init__.py`, load sort and
  `_pattern_specificity`; `arch/eval/fusion.py`, `rewrite`).
- Every implementation entry needs a source anchor in the framework's code, of
  the form `path[:line[-line]]`, and every binding records the release it was
  read at as `{repo, tag, commit}` `[code]` (`_append_op_implementation`,
  `SourceAnchor.parse`, `_audited_at`).
- The two failure directions are named. An unfused walk "OVERSTATES launches and
  activation round-trips" `[doc]` (`inference_cost_model.md`, "What the silence
  costs"). Registry fusion the framework does not run was "hiding intermediate
  HBM materialization" `[doc]` (`arch/eval/fusion.py`, `Framework` docstring).
- A dispatch condition is modelled only when it changes bytes or the main kernel
  path and triggers under common deployments; otherwise the default path is
  billed and the assumption stated `[doc]` (`inference_cost_model.md`, "How
  precisely to model a dispatch condition"). Where a framework does redundant
  work, the graph models the better form `[doc]` (same file, "Activation
  epilogues follow their consumer").
- Generic compiler fusion that cannot be anchored to source stays unmodelled;
  the source reports its measured share of bytes as small in its own corpus and
  states when to reopen the question `[doc]` (same file, "Inductor's generic
  fusion: measured, then left unmodelled").

## 4. Per-rank geometry

- Per-rank work follows from per-rank shapes, not from a per-op divisor table,
  and data parallelism "never divides work": the step time is per replica group
  `[doc]` (`inference_cost_model.md`, "Placement: per-rank shapes, not
  divisors"; `parallelism.md`, per-rank cost).
- Each stored weight declares, per stored axis, which parallel world splits it.
  A degree that does not divide the axis's part count follows the declared
  policy: `exact` refuses, `replica_cells` splits `gcd(parts, degree)` ways and
  lets ranks co-own each shard, and `pad` pads each shard to whole parts `[code]`
  (`arch/layout/weight_endpoints.py`, `_placement_layout`). A padded extent is
  rounded up to the shard quantum `[code]` (`arch/layout/layout.py`,
  `Block.padded_global_extent`), and the pricing reads that padded width `[doc]`
  (`Block.valid_counts_per_shard` docstring, "the uneven≈pad assumption").
- Context parallelism changes whose work a rank holds. The pair share a rank
  computes is the ratio of local to global causal pairs `[code]`
  (`arch/layout/physical.py`, `pairs_share`); which scheme cuts query rows and
  which cuts keys is `[doc]` (its docstring, `parallelism.md`).
- MoE expert parallelism distributes whole experts, and the expert count must
  be a multiple of the route-group size `[code]` (`arch/layout/workload.py`,
  `_check_route_group`).
  The busiest rank carries `(ρ + (k−1)(E−ρ)/(E−1)) / k` times the mean routed
  rows, for `k` local experts out of `E` and a measured expert load skew `ρ`
  `[code]` (`busiest_rank_load_factor`), under a single-hot-expert assumption
  `[doc]` (its docstring). Leaving `ρ` at its default makes routed time and
  exchange optimistic by roughly the busiest rank's excess `[doc]`
  (`known_limitations.md` §1.1).
- Storage and compute precision are separate. Weight bytes are parameters
  divided by the packing factor times the storage width, plus scale siblings
  `[code]` (`arch/eval/formats.py`, `TensorFormat.weight_bytes_for`,
  `bytes_for`). The served width of a plain float wider than 16 bits is taken as
  BF16 `[code]` (`arch/dtypes.py`, `served_dtype`). A compute pin narrower than
  its weight is refused `[doc]` (`quantization.md`, deployment precision).
- An MLA latent has no head axis, so tensor parallelism replicates it and
  raising the TP degree does not shrink its KV `[doc]` (`parallelism.md`,
  cases; `attention_families.md`, MLA).

## 5. Communication

- Collectives are grafted where the sharding state changes between producer
  and consumer: a partial result needs an all-reduce, a sharded-to-replicated
  edge an all-gather, the MoE shuffle an all-to-all, and a pipeline cut a
  send/receive `[doc]` (`parallelism.md`, "Communication is injected, and
  first-class"). The materializer was not inspected.
- Per-rank bytes are the tensor's bytes times a ring factor: `(N−1)/N`, doubled
  for all-reduce, and 1 for point-to-point. Latency hops are `ceil(log2 N)`,
  doubled for all-reduce, and 1 for point-to-point `[code]`
  (`arch/layout/comm_volume.py`, `ring_factor`, `latency_hops`).
- Each phase of a collective costs its bytes over the fabric bandwidth plus the
  link latency times its hops `[code]` (`inference/comm_cost.py`,
  `price_collective`). Bandwidths come from the card's intra- and inter-node
  peak columns `[code]` (`Fabric.of`).
- A node-spanning collective is priced hierarchically only when its op is
  scheduled that way, more than one member sits on each node and the world
  divides evenly by that count; everything else runs one inter-node ring
  `[code]` (`collective_phases`).
- The ring factor is not universal. The framework's all-reduce algorithm is
  chosen by payload from its binding `[code]` (`comm_cost.py`,
  `collective_ladder`), and each algorithm has its own hops and bytes per rank
  `[code]` (`comm_volume.py`, `ALGORITHMS`):

  | Algorithm | Hops | Bytes per rank |
  |---|---|---|
  | one-shot | 1 | `(N−1)·T` |
  | two-shot | 2 | `2(N−1)/N·T` |
  | NVLink SHARP | 2 | `(N−1)/N·T` |
  | library default | `latency_hops` | ring factor |
- The link latency and the launch floor are fixed defaults that the source
  itself calls estimates until measured `[doc]` (`inference/defaults.py`
  comments; `inference_cost_model.md`). One link latency serves every fabric,
  "a deliberate simplification" `[doc]` (same file). Collectives are not
  measured `[doc]` (`known_limitations.md` §4.8).

## 6. KV accounting

- The unit is the cached node, each sized by its own storage law and dtype;
  "There is no single 'KV bytes per token'" for a layer with several cached
  tensors `[doc]` (`kv_cache_storage.md`, "The unit of accounting").
- A cached tensor's bytes are its per-position bytes, data plus dynamic scales,
  times its positions at the cache length, divided by the ranks that share those
  positions `[code]` (`arch/eval/cache.py`, `CachedTensor.bytes_at`,
  `position_bytes`). A tensor without a law stores the full length `[code]`
  (`positions_at`). Storage and read laws are separate fields `[code]`.
- Three storage laws: per-token (grows without bound), windowed
  (`Min(s_kv, s_window)`) and constant state. A compressor stores
  `ceil(s_kv / ratio)` `[doc]` (`kv_cache_storage.md`, "Three storage laws",
  "Where the number comes from"). Per-family layouts for dense, MLA,
  sliding-window, DSA, compressed-attention and linear or state-space layers are
  `[doc]` (`attention_families.md`).
- Boundedness is judged by substituting `s_kv → ∞` into each stored length: a
  per-token tensor must grow, a windowed one must cap and a constant state must
  have no free `s_kv` `[code]` (`arch/validate/_axioms.py`, `_storage_is_bounded`,
  `_kv_growth`). A windowed family needs every growing tensor capped and at least
  one growing `[code]` (`_window_contract`). A positive configured window with no
  capped tensor fails unless the config disables windowing or the spec declares
  an exemption `[code]` (`_check_config_windowing`).
- The window gate reads stored lengths, not FLOPs, because a windowed and a
  global component emit identical attention FLOPs `[doc]`
  (`arch/validate/_type_contracts.py` docstring; `validation.md` §5.3).
- Sparse reads bill each selected row per query: exact for distinct requests,
  an upper bound under a shared prefix `[doc]` (`cache.py`, `gathered_bytes`
  docstring).

## 7. Gates before a number is published

- A spec is valid only with no gating errors `[code]`
  (`arch/validate/_orchestrator.py`, `_evaluate_spec`). Shape and dimension-map
  mismatches, the storage-byte checksum (zero tolerance), packing, the weight
  ledger, KV type contracts, KV growth claims and the window contracts all gate
  `[code]` (`_gating_errors`).
- Uncertainty is not a pass. A claim that cannot be judged is reported as a
  gating finding, a crash in a gating check fails the gate, and an analysis
  replay skipped because earlier gates failed is reported `not_run`, never
  `passed` `[code]` (`_axioms.py` unjudged findings; `_guarded`;
  `_downstream`).
- The replay checks that per-row bytes add up to the row's access and that the
  rows add up to the phase's FLOPs, access and writes, as exact integers `[code]`
  (`inference/sol_closure.py`). It does not check that per-op times add up to the
  phase time.
- The verification classes: per-op axioms (A), conservation (B), perturbation
  invariants (C), type contracts (D) and dual-path cross-checks (E). Class A
  "cannot verify itself", and "Rules marked *not implemented* provide no coverage
  and must not be counted" `[doc]` (`validation.md` §8–14).
- To anchor a per-op axiom: read the framework or model source, compute one
  layer by hand, diff the engine per axis, and fix the abstraction rather than
  adding a per-model case `[doc]` (`validation.md` §9.2).

## 8. Measured envelope, beside the roofline

- A measured row is keyed by op signature, projected shape, dtype environment,
  device and phase, not by framework, model or deployment `[code]`
  (`inference/op_calibration.py`, `PhysicalKey`).
- `envelope` mode takes the fastest row at a key after peak-drift scaling;
  `latest` takes the framework's exact declared kernel at its newest measured
  release, and reports ambiguous or missing instead of substituting `[code]`
  (`physical_time_for`, `latest_time_for`, `select_time`).
- A row measured under different peaks is rescaled by the ratio of the bound it
  saturated; without a known compute peak the ratio is 1 `[code]`
  (`_peak_drift_scaled_latency_us`, `_compute_drift`).
- A row is flagged as an anomaly when its latency falls below a fixed fraction
  of the roofline computed at the row's own test-time peaks and the caller's
  numerators, and the measured value is never clamped `[code]`
  (`ANOMALY_THRESHOLD`, `_roofline_at_test_us`, `_build_measured_timing`).
- The calibration overlay keeps the roofline as the op time `[code]`
  (`inference/calibration_overlay.py`, `CalibrationOverlay.apply`); measured
  times are published beside it, "never overwriting it" `[doc]` (`inference_cost_model.md`,
  calibration).
- Envelope selection does not filter on the numeric cross-check, so a row never
  cross-checked can win `[code]` (`physical_time_for`).
- No configured service, a working service and a failing service are three
  distinct outcomes; a failure is not an empty answer `[code]`
  (`measure/lookup.py`).
- A measured total is all-or-nothing, and because collectives are not
  measured, a deployment's measured total "cannot be complete whenever it
  contains a collective" `[doc]` (`known_limitations.md` §2.3, §4.8).

## 9. Stated limits

All `[doc]` unless marked:

- No inter-kernel overlap and no pipeline bubble (sections 1 and 2 above).
- One weight placement per spec can under-bill a framework's weight read and
  over-bill one all-gather (`known_limitations.md` §1.3).
- Disabled providers can leave the envelope slower than the fastest kernel a
  framework runs (§4.9).
- Behaviour "that lives only in weights or custom runtime code is out of reach"
  (`README.md`, Scope).
- Scope is decoder-only, optionally multimodal; encoder-decoder and
  mixture-of-depth models are out (`design.md` §1.4).
- Shape checks "prove the tensors compose, not that the graph computes what
  `forward()` computes" (`design.md` §2.3).

## 10. Where this skill departs from the source

- **Labels.** The source publishes the serial per-op sum as its SOL; it is
  reported here as the serial estimate. The resource-total maximum, which the
  source's own comment calls a bound, is reported as the conditional bound
  (section 1).
- **Unmeasured terms.** The link latency, which adds to a collective's byte
  time, and the launch floor enter the estimate only, as stated assumptions,
  never the bound.
- **Peaks.** A bound needs the peak at the clock the device actually runs that
  work at, as the source requires; a spec sheet computed at a lower clock is
  not one. A measurement above the peak means the peak definition is wrong.
- **Collective bytes in the bound.** The bound takes the fewest bytes among the
  algorithms the framework and fabric admit, since any of them could run.
- **Decode at an average length.** Evaluating decode at the average cache
  length gives the time at the mean length, not the mean time. These differ
  when an op changes its binding resource during the generation (this
  document's inference).
- **Attention work.** Causal pairs count about half of `seq²` in prefill. The
  `seq²` formula in `performance-ceiling-analysis` is given for DiT, whose
  attention is bidirectional, where it is right. Applied to causal LLM prefill
  it would overstate attention work by about 2× (this document's inference);
  that skill is not changed here.
- **Tool vocabulary.** The source's spec format, field names, default
  constants, framework line citations and model-specific figures are not carried
  over.

## 11. What this reference does not establish

- No local execution of any kind: no accelerator, no model and no run of the
  source project.
- No comparison of a predicted serving figure with a measured one exists in
  the inspected scope.
- The source's measured corpus and its figures are not reproduced or cited as
  facts.
- Files not inspected are listed in the identity record; behaviour that lives
  in them is `[doc]` above.
