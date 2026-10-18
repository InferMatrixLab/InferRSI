# Drama3 NPU task readiness — knowledge/instrument supplement

**Governing Issue:** [#27](https://github.com/InferMatrixLab/OmniRSI/issues/27) ·
**Acting parent agent:** Cursor agent (Claude Opus 5.5) under `@Dong1017` ·
**Status:** preparation supplement (Issue §7 outcome 1). This document is
source-grounded guidance and a qualification handoff. It is **not** Drama3 NPU
support, NPU validation or a performance result.

Scope of this delivery (N0–N2 preparation): source inspection, documentation and
knowledge amendments, one CPU-only contract fixture, and matrix links. Hardware
runs, environment installation, standalone-engine implementation and kernel
generation are **out of scope** and remain for a separately authorized execution
scope. Merge, goal acceptance and closure are separately authorized.

This supplement reconciles against current `upstream/main`
`d51c941dc57807c1e16ea698cd9291f414110c45`, which equals the RFC's `d51c941`
inspection pin (no reconciliation delta).

---

## 1 · Source lineage and reuse

Three records describe the same GPU design family. They share lineage and do
**not** independently corroborate one another, and none is NPU evidence.

| Source | Pin | Role here | Status |
|---|---|---|---|
| [david6666666/drama-3-single-b300-inference](https://github.com/david6666666/drama-3-single-b300-inference/tree/58a1882a4d941f8d21bfce6be37d3d5e7c9fde80) | `58a1882a` (RFC-pinned) | GPU reference engine motivating the NPU questions; Python engine with persistent request state, CUDA Graphs, incremental audio decoding, native FP8 routed experts | external source; inspected only at the RFC-selected commits below |
| [`vllm_omni.cuda.audio.concurrency_scaling_state_and_overlap`](../src/omnirsi/data/repo_packs/vllm_omni/knowledge/cuda/audio/concurrency-scaling-state-and-overlap.json) | vllm-omni `fish_omni@d6ed4f4` | Existing imported record for the same audio design family (stage/state ownership, mixed prefill, codec overlap, workspace isolation, prefix reuse, FP8 MoE) | `imported`, `locally_verified=false`, CUDA |
| [`evidence/drama3-b300-scale150/`](../evidence/drama3-b300-scale150/) | issue #10 campaign | Frozen GPU plan + validator + diagnostic lessons from the GPU campaign | campaign **INCONCLUSIVE**; GPU-only |

RFC-selected commit chain inspected for this supplement (direct inspection
limited to concrete questions; no broad history scan, no readset expansion):

| GPU case | Commit / artifact | NPU question carried forward |
|---|---|---|
| Partial-prefill state repair | [`a6e660cc`](https://github.com/david6666666/drama-3-single-b300-inference/commit/a6e660cc3693c61e14f4ed5acf75e3ac249294f0) | Can every live/padding/scratch region be distinguished and tested for noninterference on the target? (contract in §3; CPU fixture below) |
| Async codec guard | [`ec51ba1e`](https://github.com/david6666666/drama-3-single-b300-inference/commit/ec51ba1e24300718bfbbfa078f5a16e49e1c03bb) | What owns workspace/persistent buffers on the NPU runtime; what capture/ordering rules apply? |
| Cross-stream frame lifetime | [`a7118fb7`](https://github.com/david6666666/drama-3-single-b300-inference/commit/a7118fb7eb748d08c3b774fa6c9189b6eab0d9cc) | Do producer/consumer deps, allocation lifetime and replay addresses stay valid across async work? |
| BF16 FMA semantic repair | [`6ff8d808`](https://github.com/david6666666/drama-3-single-b300-inference/commit/6ff8d8067fb6e96804f49fd4f0c9020fd315e1fc) | Are contraction/accumulation/quantization/layout and state-update semantics preserved beyond algebraic equivalence? |
| Exact prefix reuse service screen | [`native-row-reuse-service/summary.md`](https://github.com/david6666666/drama-3-single-b300-inference/blob/58a1882a4d941f8d21bfce6be37d3d5e7c9fde80/evidence/20261016-ceiling/results/native-row-reuse-service/summary.md) | Do planning/mapping/memory/transfer/drain costs erase local graph savings? |
| Shared reference-code adapter / result limits | [`33f6d723`](https://github.com/david6666666/drama-3-single-b300-inference/commit/33f6d7237196520be9f457d86df161264cbb087e) · [`current-results.md`](https://github.com/david6666666/drama-3-single-b300-inference/blob/58a1882a4d941f8d21bfce6be37d3d5e7c9fde80/docs/current-results.md) | Do baselines receive equivalent inputs; are failed/incomplete runs and baseline revisions retained? |

Reused OmniRSI material (amend/relink, not duplicate): Ascend/CANN skills
(`ascend-model-adaptation`, `ascend-graph-mode`, `ascend-aclgraph-capture-replay`,
`ascend-operator-tuning`, `ascend-device-health`, `cann-attribution-overlap`),
TorchNPU allocator skills (`torchnpu-device-memory-lifecycle`,
`torchnpu-pinned-host-memory-lifecycle`), measurement/evidence skills
(`inference-benchmark-design`, `dense-performance-evidence`, `rsi-evidence`),
and the omni/audio records
([`stage_ownership_and_search`](../src/omnirsi/data/repo_packs/vllm_omni/knowledge/common/omni/stage-ownership-and-search.json),
[`streaming_serving_measurement`](../src/omnirsi/data/repo_packs/vllm_omni/knowledge/common/audio/streaming-serving-measurement.json)).

---

## 2 · Stage and state execution map (Deliverable A)

Drama3's pipeline stages, mapped to existing knowledge and the NPU gap class.
**Every NPU column is `unverified`**: the GPU/import records establish source
facts only. Gap class is one of *knowledge* (K), *code integration* (C),
*environment information* (E) or *measurement* (M).

| Stage | Entry / operator / dtype / persistent state (source facts) | Existing knowledge | NPU status | Gap class |
|---|---|---|---|---|
| Reference preparation | Reference audio/codes + text encoded once; with reference codes `benchmark.py` sends `ref_audio_codes` (vllm/standalone) or `references[vq_codes]` (sglang), with inline audio `ref_audio` (vllm) or `references[{audio}]`; cold inline-audio has a separately stated cost | `concurrency_scaling_*`, `streaming_serving_measurement` | unverified | K + E |
| Backbone (mixed prefill/decode) | Chunked prefill, async CPU scheduling, FULL decode graphs + PIECEWISE mixed graphs; per-request state indices | `concurrency_scaling_*`; `ascend-graph-mode`, `ascend-aclgraph-capture-replay` | unverified | C + M |
| GDN / recurrent + full attention | Recurrent + convolution state per request; independent GDN **suffix** sequence per padded row; teacher-forced prompt tower | `concurrency_scaling_*` (state ownership); commit `a6e660cc` | unverified | C + K |
| MoE | Native FP8 routed experts (all 8 routed), per-call routing metadata can permute physical rows; BF16 dense weights | `concurrency_scaling_*` (FP8 MoE); `ascend-operator-tuning`, `ascend-model-adaptation` | unverified | C + M |
| Codebook / acoustic generation | Autoregressive acoustic frames; sampling counters; next-frame positions | `concurrency_scaling_*` | unverified | K + M |
| Codec | Stateful streaming codec; shared capture workspace risk; chunk ramp/left-context; FP32 codec params | `concurrency_scaling_*`; commits `ec51ba1e`, `a7118fb7`; `torchnpu-*` | unverified | C + M |
| PCM delivery | 44100 Hz mono 16-bit PCM; **2048 samples per acoustic frame**; queued PCM drain is part of completion | `streaming_serving_measurement`; `benchmark.py` | unverified | M + E |

Source deployment comments are not local benchmark evidence; resolve effective
stage settings, graph buckets, precision and dependencies from the selected
target revision. Mapping the pipeline does not require implementing every path.

---

## 3 · State and execution correctness contract (Deliverable B)

Target-independent invariants (reused from the imported record's L0 plan and the
pinned commits) and the target-dependent checks still required.

### Invariants

1. **Noninterference:** live requests, padding and scratch must not overwrite one
   another's recurrent, KV, convolution or codec state.
2. **Ownership through boundaries:** partial batches, bucket boundaries,
   cancellation, EOS, maximum length and slot reuse preserve state and output
   ownership.
3. **Async validity:** every asynchronous read has a valid producer dependency and
   buffer lifetime; graph outputs survive until their consumers finish.
4. **Capture/replay compatibility:** compatible shapes, addresses, workspace and
   fallback behavior between capture and replay.
5. **Arithmetic:** precision/layout conversion, accumulation/rounding and complete
   state updates checked against an appropriate reference (beyond algebraic
   equivalence).
6. **Audio completion:** completion includes queued PCM drain; model-slot release
   is not response completion.

### Representative path made concrete: partial-batch prefill noninterference

Grounded in commit [`a6e660cc`](https://github.com/david6666666/drama-3-single-b300-inference/commit/a6e660cc3693c61e14f4ed5acf75e3ac249294f0).

- **Setup / inputs:** a batched prefill graph of fixed width `B`. `count < B` real
  requests occupy live primary slots; `B - count` padding (dummy) rows fill the
  batch. Each processed row owns a **primary** state slot and an independent **GDN
  suffix-scratch** slot derived by a mirror offset. Other in-flight requests hold
  recurrent/conv/KV state in unrelated slots.
- **Expected invariant:** after the padded prefill, every live request's
  recurrent, convolution and KV state is byte-identical to its pre-prefill
  snapshot; padding primaries **and** their suffix-scratch slots are disjoint from
  all live primaries and suffixes.
- **Failure signal (historical):** the original engine assigned padding primaries
  from the top of a `2*primary` arena; a mirror-region primary's suffix folded
  back into the primary region and overwrote a live request's state. The repair
  reserves a dedicated padding band plus separate suffix mirror space and rejects
  any padding/live overlap.
- **CPU fixture:** [`tests/test_drama3_prefill_noninterference.py`](../tests/test_drama3_prefill_noninterference.py)
  is a pure-Python reference arena that **reproduces the collision** with the
  original top-of-arena assignment (a live request's state is overwritten) and
  **preserves all live state** with the reserved-band layout, across partial
  counts `{5,6,7}`, plus an explicit overlap-rejection check.
- **Target-dependent checks still required (not covered by the fixture):** real
  recurrent/conv/KV tensors on the selected NPU runtime; ACL/CUDA-graph
  capture-vs-replay snapshots of untouched slots (replay-specific writes are
  invisible to eager-only checks); real GDN suffix allocation on-device; slot
  reuse across two generations. **The fixture carries no NPU arithmetic,
  graph-safety or allocator credit.**

### Representative path: one decode step

- **Inputs:** a decode batch with per-request recurrent/conv state, sampling
  counters and next-frame positions; decode-first ordering in a mixed step.
- **Invariant:** each convolution/recurrent state advances exactly once; fresh
  state rows reset without affecting other requests; sampling-row and RNG counter
  ordering preserved in deterministic controls.
- **Failure signals:** cross-request state advance, RNG counter drift,
  capture-stream workspace corruption (`ec51ba1e`), consumer reading a freed
  producer buffer (`a7118fb7`).
- **Target-dependent checks required:** on-device capture/replay parity, dedicated
  codec capture workspace, cross-stream producer lifetime, BF16 FMA/accumulation
  parity against a higher-precision reference (`6ff8d808`).

Reuse the imported record's L0–L4 `validation_plan` for the broader matrix; CPU
fixtures establish contract/reference logic only.

---

## 4 · Measurement and quality contract (Deliverable C)

Reuse the pinned GPU benchmark client
[`src/drama3/benchmark.py@58a1882a`](https://github.com/david6666666/drama-3-single-b300-inference/blob/58a1882a4d941f8d21bfce6be37d3d5e7c9fde80/src/drama3/benchmark.py)
and the existing frozen validator
[`evidence/drama3-b300-scale150/validator/validate.py`](../evidence/drama3-b300-scale150/validator/validate.py).

**What interoperates (no request/record adapter):** `benchmark.py` emits
`summary.json` and per-run `{label}.jsonl` records (`sample_id`, `request_id`,
`audio_samples`, `ttfa_s`, `last_audio_s`, `completion_s`, `rtf`,
`acoustic_frames`, `audio_duration_s`, `audio_sha256`, `success`, `http_status`;
summary `concurrency`/`repeat`/`makespan_s`/`throughput_frames_s`/`ttfa_p50_ms`/
`ttfa_p95_ms`/`rtf_mean`/`valid`/`failed`/`requests`/`completed`). These are what
the validator's **`load_runtime`** record/summary checks consume (frame/duration/
RTF/TTFA/throughput recomputation and completeness). The client's
`--backend {sglang,vllm,standalone}` already shapes the request body for
vLLM-Omni and SGLang-Omni, so both are drivable without a wrapper.

**What is NOT reusable as-is (identified target gap):** the validator's
`validate()` entrypoint is bound to the GPU issue-#10 campaign — it loads the
fixed `../plan/plan.json` (B300 `target_frames_s`), requires run controls, corpus
SHA and baseline SHA to equal that plan, enforces the **1.5× gate**
(`t >= b * 1.5`), and consumes a separate `evaluate_audio` quality document
(`asr`/`groups`/`wer`/`similarity`). A Drama3 NPU run therefore needs a
**target-specific plan and verdict** (and a quality-document producer), owned by
the next authorized scope — not a reuse of this frozen GPU verdict. See §5.

Frozen semantics (source-defined; reuse as-is):

- **Frame:** `returned_waveform_samples / 2048`, excludes EOS. Do not inherit a
  samples-per-frame constant blindly — it is the codec contract value `2048`.
- **Audio duration:** `samples / 44100` (44100 Hz mono 16-bit PCM).
- **Throughput:** `Σ samples / 2048 / makespan`, where makespan is the **complete
  measured window including fill/drain and failed requests**.
- **TTFA:** dispatch to first usable audio chunk; transport/encoding boundary
  stated. Report p50/p95 from enough request samples.
- **RTF:** per-request dispatch-to-last-audio / returned audio duration; state
  run-mean/repetition aggregation.
- **Warmup / connection:** `max(warmup, concurrency)` warmup requests, fresh TCP
  per request, no retries; optional reference warmup separated.
- **Quality:** score every output (WER corpus + speaker similarity), retain
  invalid/empty/truncated/excessive-silence outputs; keep failed requests,
  incomplete repetitions and unknown finish reasons. Never fabricate successful
  measurements.

**Baseline eligibility (explicit):** eligible comparators are exact vLLM-Omni /
SGLang-Omni revisions on the target, plus the standalone engine where authorized.
An unsupported/unverified combination stays explicit, not counted as zero
throughput. A ratio against one engine is not a ratio against the best eligible
baseline.

**Kept TBD (resolve before any dependent execution or performance claim; a missing
value is a blocker or explicit unknown, never a passed check):** hardware
(NPU vendor/SKU/count/IDs/HBM/host), software (driver/firmware/CANN/torch_npu/
runtime revisions, container digest), model (Drama3 checkpoint/config/tokenizer/
codec revisions, precision policy), service (streaming behavior, voice refs,
language/length range, concurrency set, caps, cancellation), evaluation
(workload revision, WER/SIM tool + tolerance, latency constraints, repetition
plan), authority (host/store/output locations, install permission, budget,
publication/integration authority).

The GPU campaign's historical 1.5× target, B300 hardware and README ratios **do
not** set this NPU task's objective; the service objective and latency/quality
trade-offs are frozen only by the owner before optimization acceptance.

---

## 5 · Minimal instrument supplementation and handoff (Deliverable D)

**No new request/record adapter is justified by current evidence.** The benchmark
client's record/summary schema already matches the validator's `load_runtime`
checks (§4), and the client already shapes vLLM/SGLang request bodies. Adding a
request-shape wrapper would be a placeholder. A target-specific **plan and verdict
(and a quality-document producer)** is required because the validator's
`validate()` entrypoint is bound to the frozen GPU campaign (§4) — this is an
identified gap for the next scope, not a reuse of the GPU verdict, and not a
request/record adapter. Any further adapter is warranted only if a concrete
interface gap is demonstrated on the target — for example, a response schema that
does not expose PCM headers the client expects, or a validator record field the
target cannot emit. If that occurs, follow the
[`qwen21_turbo_validation_adapter`](../examples/qwen21_turbo_validation_adapter.py)
precedent: real inputs/outputs, explicit unsupported modes, focused positive/
negative tests, no manufactured success data.

### Handoff for the next authorized agent

1. **Reusable immediately:** the state-ownership invariants and representative
   paths (§3) with the CPU contract fixture; the measurement/quality semantics
   and the `benchmark.py`→`load_runtime` record/summary mapping (§4); all reused
   Ascend/CANN/TorchNPU/measurement skills and the imported audio records (§1).
2. **Blocked / unrun target checks:** on-device prefill/decode noninterference,
   capture/replay parity, codec capture-workspace ownership, cross-stream
   producer lifetime, BF16 FMA/accumulation parity, and the full L3/L4 service +
   quality sweep. A **target-specific measurement plan, verdict and
   quality-document producer** are also required (the frozen `validate()` is
   GPU-campaign-bound). None has NPU evidence.
3. **Executable vs specification-only:** executable now (CPU) = the contract
   fixture and the existing frozen validator against recorded evidence.
   Specification-only = everything requiring the target runtime, device memory or
   graph execution.
4. **Needed next:** the §4 TBD tuple (hardware/software/model/service/evaluation/
   authority), plus owner authorization of a bounded execution scope. Until then,
   dependent qualification is blocked — not "ready to run".

### Target-dependent gaps — owner / action / blocker

| Gap | Owner | Action | Blocking condition |
|---|---|---|---|
| Hardware/software tuple | owner | Declare NPU SKU/count/IDs, driver/CANN/torch_npu/runtime revisions, container digest | No on-device check runs until declared |
| Model revisions + precision policy | owner | Pin Drama3 checkpoint/config/tokenizer/codec + precision | Arithmetic/quality checks cannot be defined |
| Service feature set | owner | Confirm streaming behavior, voice refs, concurrency set, caps, cancellation | Workload/measurement cannot be frozen |
| Comparator eligibility | owner | Name eligible vLLM-Omni/SGLang-Omni revisions + viable target paths | Baseline comparison undefined |
| Evaluation policy | owner | Approve WER/SIM tool + tolerance, latency constraints, repetition plan | No quality gate; GPU thresholds not inherited |
| Target measurement plan + verdict | next authorized scope | Author a target-specific plan/verdict + quality-document producer (frozen `validate()` is GPU-campaign-bound; `load_runtime` schema is reusable) | No eligible PASS/FAIL verdict until authored |
| Service objective (optimization) | owner | Freeze objective + latency/quality trade-offs | Optimization acceptance cannot proceed |
| Authority / budget | owner | Grant execution host/store/output, install permission, resource/time budget, publication/integration authority | Execution scope not authorized |

---

## 6 · Limitations and next authorization boundary

- This is a knowledge/instrument supplement. It establishes **no** Drama3 NPU
  support, NPU validation or performance gain.
- The CPU fixture validates a contract abstraction of commit `a6e660cc`; it does
  not execute Drama3/GDN/codec, graphs or NPU kernels and carries no
  arithmetic/graph/allocator credit.
- The imported audio record and GPU campaign are CUDA-only, shared-lineage and
  `locally_verified=false`; they are not independent corroboration.
- Hardware qualification and optimization proceed only after the owner authorizes
  a bounded execution scope with the §4/§5 TBDs resolved.

Permitted completion claim for this scope: **"knowledge/instrument supplement
ready for acceptance; target qualification pending."**
