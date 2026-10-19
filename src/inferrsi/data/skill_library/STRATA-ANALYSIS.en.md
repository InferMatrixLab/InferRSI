# Generating a Strata-like inference engine with AI: analysis and search space

**The main search problem is the joint design of expert placement, heterogeneous execution and state management under memory constraints.** Kernel-only tuning misses end-to-end opportunities; expanding the expert cache can consume memory needed by KV, MTP or prefill workspaces.

Here, AI generation means proposing configurations or code candidates, filtering them through an explicit evaluator, and retaining a reproducible baseline. Fix the model, hardware, workload and quality contract first. If model or hardware selection is allowed, put it in a separate outer search and redefine comparability.

The [English Skill](en/strata/SKILL.md) and [Chinese Skill](zh-CN/strata/SKILL.md) each contain design, tuning and validation branches. See the [verification record](IMPORT.md) for construction and checks.

## Separate three search levels

| Level | What AI may generate | Acceptance condition |
|---|---|---|
| Existing parameters | Legal flags/env, placement budgets, CPU workers, spec/prefill/batch settings | Activated settings, feasible memory, quality and end-to-end metrics |
| Algorithms and code | Expert admission/replacement, CPU/GPU division, prefetch, fusion, tiles, queues, checkpoints | Interface/state contracts, build/parity/concurrency checks, then measurements |
| Model and system extensions | New quantization, expert pruning, model families, general parallel or multi-node support | New implementation, reference and quality budget; not an automatically equivalent optimization |

**Not freely searchable:** a fixed checkpoint's tensor shapes, routing semantics, tokenizer, RoPE/state alignment and speculative acceptance/rollback correctness; also capacity, headroom and request semantics fixed by the hardware and use case. Changing these requires an explicitly different experiment.

## An evaluation contract for AI search

Let `H` be hardware/backend, `M` the model, `W` the workload and `C` a configuration or code candidate:

```text
minimize [TTFT_p95(C), ITL_p95(C), -throughput(C), energy_per_token(C)]
subject to:
    peak_VRAM_i(C) <= budget_i                 for each GPU
    peak_RAM(C) <= host_budget
    quality_drop(C, reference) <= epsilon
    state_correct(C) and backend_supported(C)
```

This is a proposed evaluation framework, not a complete optimizer already shipped by Strata. Use only objectives that matter and can be measured; do not invent energy results without power measurements. Interactive use emphasizes TTFT/ITL, while concurrent serving emphasizes throughput and tail latency. Their optima need not coincide.

Suggested order: memory feasibility → CPU/PCIe/expert residency → coupled prefill/KV/MTP tradeoffs → measured kernel hotspots → concurrency/multiple GPUs → approximations under a separate quality budget. Existing `tools/calibrate.py` already covers part of decode calibration; reuse it before implementing the same sweeps again.

Each AI candidate task should specify allowed files/interfaces, bottleneck evidence, a reference, quality/resource gates, fixed workloads, repeated measurements and rollback. Iterate through “generate a diff → static/build → numerical/state checks → cheap screening → full A/B → retain Pareto candidates.” An agent's verbal assessment is not the evaluator.

The following provides source evidence and 15 dimensions. It is a fixed-revision source analysis, not a reproduction of upstream advertised throughput.

---

## Detailed repository evidence

Baseline: `Niko1221/Strata`, commit `296b59d2f73c8f04a805df29c2fa97655adace78`, inspected 2026-10-14; CMake version `0.1.44.1`. This is a source inspection, not an independent reproduction of upstream speed or quality measurements. Evidence links are pinned to that commit.

Contents: scope; execution flow; search dimensions; dependencies; numerical contracts; experiment design; evidence index.

## 1. Scope and architectural identity

Strata's main path is a model-specific heterogeneous inference engine: it combines GPU dense/state computation, a GPU tier of frequently used MoE experts, CPU computation of other experts, optional transfer of some misses to the GPU, and SSD-backed n-gram lookup. Its primary design opportunity is **joint placement and execution scheduling under constrained memory**, rather than only faster matrix multiplication.

For the Flash-Next path, the compiled geometry declares hidden size 2560, 48 trunk layers, 512 experts per layer and top-10 routing, with pruned variants allowed to carry fewer experts. Every fourth layer is QSA: 36 Gated DeltaNet layers plus 12 QSA layers. Four hyper-connection residual streams and PLE history are part of the state contract. These numbers describe this model path; they are not a proposal to search arbitrary model architecture while preserving the checkpoint. [E1]

Do not repeat the stale documentation statement that only one model is executable. The current source also dispatches `qwen35moe` to a separate Qwen3.6-35B-A3B CUDA/HIP path. Its options and capabilities must be checked independently. CUDA and HIP are build choices; SYCL is a separate experimental backend. Metal is a newer implementation with its own kernels and memory behavior; the Mac documentation reports measurements on two Macs, not universal backend parity. [E2–E4]

## 2. Execution flow

**Control plane.** The Python `StrataEngine` launches the executable with `--serve` and exchanges text commands and token events over subprocess pipes. The default server queues requests; optional batch slots maintain independent sequence states and execute rows together. API compatibility, tokenization, chat templates, cancellation, and admission are a separate layer from kernel scheduling. [E5, E16]

**Model/state preparation.** GGUF metadata is checked against the family and compiled geometry. Dense projections, shared experts, routers, residual machinery, output head, session state and optional MTP occupy device memory; an expert profile seeds the GPU expert tier. The main Flash-Next host path can pin the expert arena, map expert files, or retain a RAM complement/budget. PLE rows are fetched through a bounded reader and cache. Actual runtime defaults may differ from bare `Options` defaults because setup, architecture defaults, flags and environment variables intervene. [E1, E6, E19]

**Prefill.** Read prompt tokens in chunks. Dense projections use matrix-matrix kernels, recurrent layers advance through the chunk, and routed rows are grouped by expert. Resident experts are consumed in VRAM; other experts stream through a copy-stream staging ring. The prefill workspace may temporarily borrow expert-cache capacity and refill it before decode. For short chunks, a conditional CPU-sharing path also exists. A larger chunk amortizes expert transfers but consumes workspace and can delay other requests. [E7, E8]

**Decode/verification.** MTP or suffix lookup proposes tokens. A verify window runs the accepted input token and proposals through the trunk. Within each layer, repeated expert IDs across rows are deduplicated. Work is split among GPU-resident hits, a selected PCIe share of nonresident experts, CPU jobs, and optional peer/helper GPU jobs. The GPU plan is published first so CPU and GPU work overlap. This is more accurate than saying every cache miss is executed on the CPU. [E9, E10]

**Handoff.** Captured GPU graphs and mapped pinned doorbells exchange activations, routes, sequence numbers and completion flags with the CPU pool. Windows driver submission behavior is explicitly handled by querying the driver while polling; replacing the handshake with an unqualified memory spin is not equivalent. [E11]

**Speculative commit.** Verification tentatively appends KV/indexer entries, while accepted-prefix commit advances recurrent/conv state, repairs indexer tails and restores the appropriate PLE history. Rejected KV cells can be overwritten only before a future query consumes them. MTP has private KV and its own residual/token alignment. A draft policy compares expected accepted tokens per measured round time for MTP and suffix lookup. [E12–E14]

**Adaptive residency.** The host counts routed experts, compares hot misses to cold residents within each layer, sorts proposed swaps by gain and limits swaps per round. Counts decay. Overlap is guarded by per-layer copy completion, so a residency pointer never grants access to bytes that have not landed. Cache storage and adaptive replacement policy are distinct responsibilities. [E6, E15]

## 3. Search dimensions

The following is a structured space, not a Cartesian product. **Setting** means a knob already exists; **replacement** means modifying code behind an existing contract; **extension** means a capability that must be implemented and validated.

| Dimension | Existing settings or mechanisms | Replacement/extension candidates | Main tradeoff and gate |
|---|---|---|---|
| Model and arithmetic contract | GGUF family checks; native quantized packs; supported Q2/IQ/K quant paths; conditional NVFP4 support | New quant formats, arbitrary model families, general operator IR | Weight bytes, bandwidth, quality and kernel coverage. A new geometry is not just a configuration change. |
| Memory placement | `--expert-cache`, `--expert-profile`, `--vram-reserve-mib`, `--mmap-experts`, `--resident-experts`, `--resident-budget-gib` | Learned or cost-aware placement; allocation across layers based on marginal benefit | More experts in VRAM reduce CPU work but compete with KV, MTP and prefill buffers. |
| Replacement policy | `--adapt-every`, `--adapt-swaps`, `--adapt-decay`, `--adapt-min-gain`, `--adapt-async`, profile save | LRU/LFU variants, bandwidth-aware admission, reuse-distance prediction | Swap bytes and staleness versus hit benefit; preserve pointer/table validity and avoid evaluation-trace leakage. |
| CPU/GPU division | `--pcie-frac`, `--pcie-mode auto/dma/kernel/direct`, automatic share refinement; GPU hit groups and CPU miss groups | Per-layer or workload-specific cost models; new split heuristics | CPU RAM bandwidth versus PCIe plus GPU cost; valid pinned sources and staging capacity are prerequisites. |
| CPU scheduling | `--pool-workers`, `--pool-tasks`, `--pool-affinity`, `--host-core`, `--aux-cpus`, row-split multi-token jobs | NUMA-aware placement, different task granularity | Too many workers can starve control/copy threads or saturate memory without increasing throughput. |
| GPU kernels | Native GEMV/MMVQ, grouped expert kernels, fused GR/GDN, QSA selection and attention, architecture-specific prefill paths | Tile/warp layout, vector width, reduction tree, split-K, fusion boundaries | Registers, shared memory, occupancy and memory traffic; changed reductions need explicit numerical validation. |
| Prompt processing | `--prefill N/auto[:N]`, `--short-read`, `--no-prefill-borrow`, `STRATA_PREFILL_RING`, `STRATA_PREFILL_CPU_SHARE` | Chunk scheduler, transfer lookahead, ring sizing, phase-aware workspace allocation | TTFT, transfer amortization and concurrent decode latency; backend-specific ceilings apply. |
| KV/state | `--kv fp16/int8/q4_0/k8v4`, `--kv-resident`, `--kv-grow`; pooled QSA selection and recurrent state | Page replacement/prefetch policy; other quantization layouts | KV memory versus expert capacity and transfer latency. Reduced precision changes the numerical contract. |
| Speculation | `--spec`, `--mtp`, `--mtp-window`, `--spec-min-p`, `--mtp-max-t`, `--suffix-draft`, `--lookup-chain` | Draft-source selection, adaptive depth, cost/acceptance estimator | Accepted tokens per total round time, not acceptance alone; account for extra model/state memory. |
| Sampling | Greedy, temperature/top-k/top-p/seed; coupled/probabilistic draft mechanisms | Alternative exact rejection algorithms or separately approved sampling changes | Same-seed output equality and distributional correctness are different contracts. |
| Conversation reuse | `--prompt-cache`, checkpoint interval/root/tail, conversation RAM budget/slots, session files | Reuse-aware eviction or checkpoint placement | Prefill saved versus host RAM/copy cost; recurrent/indexer/PLE state must match the reused token prefix. |
| PLE/I/O | `--ple-io`, `--ple-row-cache`, `--ple-inflight`, prefetch controls | Request coalescing, cache policy, storage layout | Random-read latency and queue depth; rows must correspond to correct n-gram history. |
| Multi-GPU | `--layer-split`, `--split-device`, peer tier, remote expert caches, `--trim-stage-weights`, pipeline windows | Topology-aware stage cuts and expert placement | Link bandwidth and stage balance; present mechanisms are not a general tensor-parallel or multi-node runtime. |
| Serving/batching | `--batch`/slots, `--batch-mtp`, `--batch-groups`, prompt/decode time sharing, Python request queues | Admission/SLO policies and broader continuous-batching strategies | Throughput versus per-request latency, fairness and per-slot state memory. Existing batch support must not be described as absent. |
| Elastic resources | `--vram-elastic`, segment size; `--kv-grow` | Unified budget controller across caches/state | Stable virtual addresses, valid physical mappings, bounded headroom; these two modes are not universally composable. |

Record each field's legal range from the selected revision; the names above identify candidates, not a universally valid launch command. Useful baseline declarations are in `src/program/generate.cpp:337–680`; parser and activation guards determine what is actually enabled. [E17]

## 4. Important dependency constraints

- **Geometry:** dimensions, number of experts selected and residual/state structure come from checkpoint semantics and compiled kernels. Changing them belongs to model/engine co-design and requires a new correctness baseline. [E1]
- **Memory budget:** per device, require `dense + state/KV + MTP + graph/scratch + prefill workspace + resident experts + reserve <= usable memory`, counting temporary overlap and loans once, at their actual lifetime. Host budgets include expert copies or complements, pinned KV, parked conversations and I/O caches. [E6–E8, E17]
- **Streaming versus growth:** `--kv-grow` is gated to one GPU, nonstreaming KV, a profile-filled cache, all experts in RAM, VMM availability, no batch, no VRAM elasticity, no peer and no remote cache in this Flash-Next implementation. Unsupported combinations can be disabled with a warning; the requested flag is not proof of effective activation. [E18]
- **Streaming floor:** the current resident-KV floor is 20,480 cells; it covers a verify window's possible selected cells plus working needs. A search cannot set an arbitrarily tiny resident pool and assume equivalent behavior. [E20]
- **Speculation limit:** `kVerifyMaxT = 8` is the compiled window limit, including the input row; `--spec 4` means at most three proposals. Increasing this is an implementation change, not a safe unbounded integer sweep. [E13, E21]
- **Batch MTP:** needs serving, at least two slots, MTP and a speculative window of at least two. It does not combine with pipelined batch groups above one; layer-split helper-cache combinations are gated. Ordinary batch windows have a row cap and per-slot state costs. [E16]
- **RoPE:** scaling is a process-level state contract because cached keys are post-RoPE. Mixing per-request scaling in one cache without rebuilding state is invalid. [E17]
- **Copy/graph contracts:** captured pointers must remain valid across cache loans, eviction, KV growth and elasticity. Swaps must not expose uncompleted copies. Handoffs require actual producer/consumer ordering, not just matching struct layouts. [E6, E11, E15]
- **Backend specificity:** CUDA, HIP wave32, gfx906 compatibility, SYCL and Metal do not imply equal feature support or identical defaults. Confirm kernel and host-path support for each candidate. [E3, E4]

## 5. Numerical correctness: do not call everything lossless

Separate three targets: (a) bit-identical logits/state or token equality under a fixed deterministic path; (b) equivalent target sampling distribution with potentially different same-seed samples; (c) an explicitly budgeted quality change.

The verify implementation documents exact per-token arithmetic for its reference path, but that is not a blanket guarantee for every active optimization. In particular, `STRATA_ROUTE_TAIL_SKIP` skips a nonresident expert when its best rank across the window is below the chosen importance threshold; its contribution becomes zero without renormalizing the others. Conditional CUDA and gfx12 serving defaults can turn it on. It is suppressed in several cases, including nearly all experts cached, NVFP4 by default, and batch slots for default activation; the dispatch excludes peer/helper cases. **It changes logits.** Set an explicit reference mode when claiming exactness. [E10, E22]

KV quantization, resident-biased routing, speed-projection vectors, altered precision/reduction paths, and some CPU/GPU prefill-sharing choices also require their own error or parity assessment. In contrast, lowering draft-only precision can remain target-correct if verification and commit retain their contract, although acceptance and runtime change. Probabilistic speculation uses rejection probabilities and residual sampling against the post-penalty/post-filter target distribution; validate that distribution, not merely a few token strings. [E12, E23]

A cache or scheduling change can still expose numerical differences because CPU and GPU kernels may use different arithmetic. Do not infer bit equality from the fact that the mathematical expert is unchanged. Distinguish upstream comments, upstream measurements, independent tests and untested proposals in the report.

## 6. An AI generation/search loop

Represent a candidate as `C = (placement, execution split, kernels, prefill, KV, speculation, scheduling, reuse, I/O, approximation policy)`, conditioned on fixed `H = hardware`, `M = model`, and `W = workload`.

1. Establish a correctness baseline and a workload suite: short chat, long prefill, long decode, tool-return follow-ups, code/lookup-rich text, context lengths and concurrent arrivals. Separate profile-training prompts from evaluation prompts.
2. Build a feasibility filter from memory budgets, backend support and dependency guards before evaluating performance.
3. Start with existing settings and measure which resource is limiting. Change one mechanism or a justified interacting group at a time; keep a reproducible incumbent.
4. Use code generation for the confirmed limiting algorithm/kernel, with a narrow contract and a paired reference implementation. Kernel microbenchmarks are a screening step; end-to-end validation remains necessary.
5. Rank a Pareto frontier of TTFT, p50/p95 inter-token latency, generated tokens/s, concurrent throughput, peak RAM/VRAM, startup cost and quality. If energy matters, measure it rather than substituting nominal TDP.

A useful approximate reasoning model is `T_window ≈ T_fixed + Σ_layer max(T_CPU_misses, T_GPU_hits+transfer, T_other_device) + T_handoff + T_draft + T_commit`. This is a bottleneck model, not an additive profiler truth: real overlap and shared links must be measured. Speculative throughput is `E[committed tokens] / E[total round time]`; the source's lookup policy already follows this principle. [E14]

For each result record commit, backend/toolchain, model shard hashes/quant, GPU/CPU/RAM/topology, effective configuration, workload and seed, warmup/cold status, counters for experts/bytes/acceptance, repetitions and paired reference. A quality-changing candidate needs an agreed quality bound and teacher-forced/logit or task evaluation; throughput alone cannot establish success.

Strata already includes `tools/calibrate.py`: it sweeps PCIe share, speculative confidence, CPU workers and adaptive-tier choices, with repeated/interleaved comparison and a minimum-gain rule. Reuse that bounded calibration before inventing an optimizer. It measures decode; it is not a full end-to-end code-generation search. [E24]

Suggested ordering: first memory feasibility and an explicit numerical baseline; then expert placement/CPU–PCIe balance; then prefill chunk/workspace and speculative window jointly; then measured kernel hotspots; finally multi-GPU/serving policy if the target workload needs them. Search changes to model semantics only in a separately budgeted approximation track. This ordering is a recommendation from the observed architecture, not a claim that all hardware has the same bottleneck.

Extensions not established by this inspection include arbitrary-model execution through a general compiler IR, general tensor parallelism, multi-node collectives, a global automatic search framework, and a universal SLA scheduler. Conversely, multi-GPU placement, prompt lookup, batch slots, batch MTP, KV streaming and elasticity already have implementations; do not present them as entirely new ideas for this repository.

## 7. Evidence index

All links below use the inspected commit. Line spans are intentionally short enough to find the relevant contract; follow the implementation when changing it.

- **E1** [Compiled geometry and family/state contracts, `geometry.hpp:20–76`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/core/geometry.hpp#L20-L76).
- **E2** [Family dispatch, `generate.cpp:1867–1879`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/program/generate.cpp#L1867-L1879), [Qwen3.6 path contract](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/qwen35/engine.hpp#L1-L10).
- **E3** [Version/SYCL build guard, `CMakeLists.txt:10–23`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/CMakeLists.txt#L10-L23), [HIP choices, lines 59–94](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/CMakeLists.txt#L59-L94).
- **E4** [Metal scope/status, `docs/MAC.md:1–38`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/docs/MAC.md#L1-L38).
- **E5** [Subprocess boundary, `serve/server.py:816–824`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/serve/server.py#L816-L824).
- **E6** [Expert storage/profile and stable-address elasticity, `expert_cache.hpp:37–134`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/core/expert_cache.hpp#L37-L134).
- **E7** [Prefill contract, `prefill.hpp:1–10`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/prefill/prefill.hpp#L1-L10), [prefill borrowing, `generate.cpp:534–550`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/program/generate.cpp#L534-L550).
- **E8** [Short-prefill sharing and ring sizing, `prefill.cpp:164–206`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/prefill/prefill.cpp#L164-L206), [ring, lines 292–313](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/prefill/prefill.cpp#L292-L313).
- **E9** [Expert deduplication and CPU/GPU work plan, `expert_source.cpp:3715–3745`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/core/expert_source.cpp#L3715-L3745).
- **E10** [Tail skipping and pinned PCIe routing, `expert_source.cpp:3747–3818`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/core/expert_source.cpp#L3747-L3818).
- **E11** [Mapped pinned doorbell and driver polling, `layer.hpp:410–440`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/core/layer.hpp#L410-L440).
- **E12** [MTP alignment and draft-only arithmetic, `mtp.hpp:1–19`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/core/mtp.hpp#L1-L19).
- **E13** [Verify and accepted-prefix state contract, `verify.hpp:1–21`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/core/verify.hpp#L1-L21).
- **E14** [Measured acceptance/cost policy, `draft_policy.hpp:1–44`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/spec/draft_policy.hpp#L1-L44).
- **E15** [Adaptive swap selection, `generate.cpp:8833–8865`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/program/generate.cpp#L8833-L8865), [copy completion gate, `verify.hpp:42–59`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/core/verify.hpp#L42-L59).
- **E16** [Batch/MTP guards, `generate.cpp:4491–4526`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/program/generate.cpp#L4491-L4526), [batch behavior and evaluation limits](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/docs/BATCHING.md#L1-L33).
- **E17** [Options and rationale, `generate.cpp:337–680`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/program/generate.cpp#L337-L680).
- **E18** [KV growth activation, `generate.cpp:4391–4408`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/program/generate.cpp#L4391-L4408).
- **E19** [Bounded PLE reader, `ple_reader.hpp:1–12`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/ngram/ple_reader.hpp#L1-L12), [reader configuration, lines 46–63](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/ngram/ple_reader.hpp#L46-L63).
- **E20** [KV layouts, `layer.hpp:209–241`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/core/layer.hpp#L209-L241), [resident floor, `layer.cpp:666`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/core/layer.cpp#L666).
- **E21** [Window cap, `verify_kernels.hpp:21`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/kernels/verify_kernels.hpp#L21), [CPU row splitting, `pool.hpp:175–185`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/kernels/cpu/pool.hpp#L175-L185).
- **E22** [Conditional output-changing defaults, `generate.cpp:8618–8664`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/src/program/generate.cpp#L8618-L8664).
- **E23** [Probabilistic speculative distribution contract, `spec_prob.hpp:1–31`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/include/strata/core/spec_prob.hpp#L1-L31).
- **E24** [Existing calibration scope and candidate values, `tools/calibrate.py:1–44`](https://github.com/Niko1221/Strata/blob/296b59d2f73c8f04a805df29c2fa97655adace78/tools/calibrate.py#L1-L44).

## 8. Verification status

Read the relevant source, declarations, guards and repository guidance; cross-checked evidence locations and distinct existing-versus-proposed capabilities. No model download, install, build, GPU execution or runtime benchmark was performed for this analysis. Hardware-specific speed, same-seed equality and quality must be verified on the intended machine. Repository `AGENTS.md` requires measured claims, opt-in new features, and building touched backends; any later implementation should also follow the user's plan → code → test → review workflow.
