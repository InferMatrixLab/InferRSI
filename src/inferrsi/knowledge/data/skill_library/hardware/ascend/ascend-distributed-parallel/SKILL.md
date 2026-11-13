---
name: ascend-distributed-parallel
description: 'Select and validate distributed parallelism strategy on Ascend NPU: topology-aware  card-group selection, USP/CP/TP/PP strategy choice, communication masking setup and  verification, attribution of parallelism gains, and diagnosis of strategies that appear  to activate but have no effect. Covers native HCCL multi-rank AllReduce dispatch, scratch and synchronization boundaries, AlltoAllV defect workaround, and source-scoped communication-test timing and correctness coverage.

  '
---

# Selecting and validating distributed parallelism

Status: **candidate**; empirical validation: **not_run**. Source inspection,
upstream test definitions, wrapper output and native measurements are different
evidence. The retained diffusion strategy observations below are conditional on
their original workload and stack; they are not universal HCCL eligibility rules.

## Native HCCL AllReduce qualification

Use the [pinned native AllReduce procedure](references/hccl-allreduce.md) and
[exact source readset](references/hccl-allreduce-readset.json) when the question
is how a collective is selected and executed. It follows one positive-count,
multi-rank OPBASE path through `AicpuAllReduceSoleMeshOneShot`, AICPU
orchestration, peer writes, synchronization and local reduction. It does not
qualify every HCCL algorithm, device generation or the external HCOMM runtime.

1. **Establish the entry route.** Record the loaded HCCL/HCOMM build, CANN/ACL,
   device generation, communicator rank/device map, topology, count, dtype,
   reduction, stream mode and engine/cache/plugin settings. This source's open
   route has version/device gates. Empty and rank-one calls bypass the
   multi-rank mechanism and cannot validate it.
2. **Confirm the final dispatch.** At the pin, ordinary `MESH_1D` uses a cost
   selector with topology/executor filtering and possible tuner influence.
   A size threshold in another selector, a requested environment setting or an
   upstream test name is insufficient. Inspect the final algorithm/engine after
   resource or cached fallback and match it to the source before tuning.
3. **Budget scratch and preserve dependencies.** This one-shot template uses
   one chunk-sized scratch slot per rank, exchanges full chunks with peers and
   locally reduces after notifications join the work. Its executor can split
   a payload into scratch-bounded loops and a tail. Rank count, buffer size and
   dispatch changes can alter both work and memory; source accounting is not a
   measured footprint. Do not remove peer/thread waits based on enqueue timing.
4. **Check data on every rank.** Use distinct rank/position inputs, an
   operation-correct reference, explicit completion and predeclared numeric
   tolerances. Retain error logs: the inspected template logs rather than
   propagates a `PostLocalReduce` failure at one call site. Cover count one,
   odd/tail counts, reuse, application rank maps and
   observed dispatch/loop boundaries. The inspected upstream tests check
   simulated task-graph semantics; they neither compare real NPU tensors nor
   assert that their `1shot` case names selected this algorithm.
5. **Measure the relevant boundary.** Separate host enqueue, completed
   collective latency and application-stage latency; retain all ranks and the
   slowest participant for collective completion. A ring-derived bandwidth
   formula is not measured traffic for this all-peer implementation. Require
   a producer/consumer timeline for overlap and application evidence for gains.

The reference supplies exact implementation/test lines, counter-signals and an
unrun target-validation recipe. Native numerical, topology, transport,
performance and model/service qualification remain **not_run**.

## Communication-test evidence

For an isolated communication question, use the
[pinned communication-test acceptance procedure](references/awesome-ascend-communication-tests.md)
before treating a tool's PASS or bandwidth field as evidence. It distinguishes
native HCCL-test wrappers from PyTorch/HCCL call paths, maps tensor shape to
payload, and checks the actual validator and timing boundary. Its source is
awesome-ascend-skills `75ec89ce9d401be8ac95980e1c3f42f8d4315057`;
that wrapper extraction did not inspect the underlying collective implementation.
The separate native source slice above adds bounded implementation evidence;
local backends and hardware behavior remain unvalidated.
Keep the existing topology, strategy-activation and in-model attribution gates
below: a completed isolated test does not establish a parallelism or service gain.

## Card-group topology in the inherited diffusion setup

The following two/four/eight-card restrictions belong to the inherited diffusion
setup. For that setup, use the interconnect domains reported by
`npu-smi info -t topo`; for another device/topology, derive eligibility from its
runtime and selected collective rather than transferring these restrictions.

- **Valid card groups:**
  - 2 cards: one adjacent pair in the same UB/HCCS domain
  - 4 cards: one complete same-domain group
  - 8 cards: all cards
  - Cross-domain combinations were treated as **invalid for the original local comparison**. If a separately qualified comparison uses a cross-domain group, label the changed interconnect domains and remeasure bandwidth instead of mixing it with the original same-domain anchor.

- **Execution requirements** (including a mandatory four-step smoke check):
  1. Before selecting cards, use `npu-smi info -t topo` to confirm UB connectivity within the target group.
  2. Check Health with `npu-smi info`; reject Alarm cards and cards occupied by other processes.
  3. Multi-card runs require a **four-step smoke check of per-step timing uniformity**. Uniform timing inflation of roughly one order of magnitude across the group is the observed SIGKILL residual-state pattern; reset the driver or change groups. `npu-smi Health=OK` alone does not establish that a group is usable.
  4. **A card-group change is a contract change**: remeasure the anchor on the new group within the same measurement window; do not mix in values from the old group.

## Parallel strategies and selection

| Strategy | Applicable workload | Communication pattern | Key parameter |
|------|---------|---------|---------|
| Ulysses parallelism (USP) | Sequence sharding in multimodal diffusion models | all-to-all | ulysses_size |
| CFG parallelism | Classifier-free guidance enabled | Independent inference for both branches | cfg_parallel |
| Tensor parallelism (TP) | One layer's parameters exceed single-card memory | all-reduce / all-gather | tp_size |
| Ring sequence parallelism (RSP) | Long-sequence communication can overlap computation | P2P ring transfers | world_size |
| Pipeline parallelism (PP) | Many layers, with each layer fitting in device memory | send/recv | pp_size |

## Requirements for activating USP (Ulysses)

**Mechanism:** Ulysses's all-to-all head-parallel path **does not activate automatically**. Setting sequence sharding on the attention processor alone follows the non-CP path: the profile contains allGather but no allToAll.

**Observed trigger:** explicitly set every `attn.processor._parallel_config` to `ParallelConfig(context_parallel_config=cp_cfg)`. The wrapper must be `ParallelConfig`, not `ContextParallelConfig`, to activate all-to-all head partitioning.

**Verification:** require profile evidence of `allToAll`, not only `allGather`.

## Communication overlap mechanism and upper bound

### Chunked pipeline overlap

Run collectives on a separate communication stream concurrently with AI-core operators on the compute stream. Chunked pipelining divides a layer's communication into `n` head-dimension chunks and pipelines each chunk's communication and computation.

### Bound and decision criteria

Use three quantities, all measured per layer:

| Quantity | Meaning |
|---|---|
| `C` | Total communication to overlap: kernel time for the affected family divided by the number of layers |
| `F` | Computation that can run concurrently: compute time on the overlapping side divided by the number of layers |
| `n` | Number of chunks; it must divide the local head count on every rank |

Per-chunk communication is `c = C/n`; per-chunk computation is `f = F/n`. **The key ratio is `c/f`, equivalently `C/F`.**

### Case 1: `f >= c` (equivalently `F >= C`)

Computation can continuously cover the communication stream. Exposed communication is approximately the pipeline fill, or first communication chunk:

```
maximum overlap fraction = 1 - 1/n
```

This is the ideal bound: splitting heads into `n` groups can hide at most `1-1/n`, leaving one group's communication exposed.

### Case 2: `f < c` (equivalently `F < C`)

The actual bound is lower. Each communication chunk exceeds its compute chunk, leaving steady-state exposure of `c - f` per chunk:

```
minimum exposed time ≈ c + (n-1)*(c-f) + drain
maximum overlap fraction = 1 - minimum exposed time / C
```

**Implications:**
- The steady-state term is `(n-1)(c-f) = (1-1/n)(C-F)`, so increasing `n` offers little benefit when `F<C`.
- Improving overlap requires **reducing communication or increasing overlapping computation**: quantization, less cross-island traffic, merged collectives, or moving independent computation into the overlap window.
- **Decision order:** compute `c/f`, then compare measured overlap with its upper bound.

## Implementing communication overlap

All of these activation checks are required:

1. The affected operator family's **invocation count increases by approximately `n` times**; an unchanged count means the mechanism did not activate.
2. The side stream uses zero AI cores.
3. `Communication(Not Overlapped)` decreases; match the column name exactly.
4. Output MD5 is **byte-identical** to the disabled case. A pure permutation without reduction must preserve the output exactly.
5. Keep hit/fallback counters for fallback branches to detect a gate that silently falls back on every invocation.

**Submission order determines scheduling:** collectives on the same communicator execute in submission order. Submitting all forward all-to-all operations before reverse operations delays the reverse path until after that layer's computation. Use **software-pipelined submission**: submit forward chunk `g+1` before reverse chunk `g`.

## AlltoAllV defect and workaround

On some CANN versions, the split path through `HcclAlltoAllV` **SIGSEGVs**, while equal-size `HcclAlltoAll` works.

**Workaround: pad and use equal-size transfers.** Pad each input block to `S_PAD`, a multiple of 128 derived from the global `max(out_sizes)` and identical on every rank. Exchange with equal-size `HcclAlltoAll(count=S_PAD×row_elems)`, then slice the first `out_sizes[j]` rows of each block.

**Verification:** the kernel changes from `hcom_alltoallv` to equal-size `hcom_alltoall`, and the exchanged result matches the reference bit for bit.

## Determining whether a parallel scope activated

### Common silent failures

Parallel code commonly fails through **silent fallback**:

- The sharding hook did not activate, so each rank redundantly computes the entire sequence. Results appear correct but run slowly.
- Scope-depth bookkeeping disagrees with execution: small runs appear normal, while larger runs go out of bounds.
- "Applying parallelism" is logged before actual registration, so the log gives the wrong conclusion.

**Core principle:** establish that sharding happened before interpreting output correctness.

### Probe state directly (vLLM-Omni convention)

At the suspect location, print state values rather than descriptive log messages:

```python
import sys
from vllm_omni.diffusion.distributed.parallel_state import (
    get_sequence_parallel_world_size as _gsw,
    get_sequence_parallel_rank as _gsr,
)
from vllm_omni.diffusion.forward_context import get_forward_context as _fc

sys.stderr.write(
    "[probe] tensor=%s sp_world=%s sp_rank=%s sp_active=%s depth=%s\n"
    % (tuple(x.shape), _gsw(), _gsr(),
       getattr(_fc(), "sp_active", "n/a"),
       getattr(_fc(), "_sp_shard_depth", "n/a"))
)
sys.stderr.flush()
```

**Interpretation:**

| Observation | Meaning |
|---|---|
| `x.shape[0] == seq_len` | **Unsharded**; investigate |
| `x.shape[0] == seq_len // sp_world` | Sharded |
| `_sp_shard_depth == 0` | Outside the sharded scope; the full sequence is visible here |
| `_sp_shard_depth >= 1` | Inside the sharded scope |

**`_sp_shard_depth` is the reliable discriminator in this convention**; `sp_plan_hooks_applied` is often unavailable.

### Common misdiagnosis: stale topology-derived parameters

When the parallel degree changes, **recompute every parameter derived from the previous topology**: local heads per rank, chunks per rank, shard length per card, and similar values. Otherwise guards can evaluate false and silently disable the entire optimization while results and performance appear normal.

**Action:** list and recompute topology-derived parameters whenever the parallel degree changes; do not reuse values from an earlier delivery configuration.

## Topology-dependent selection

The ranking of parallel strategies can reverse across interconnect topologies. Historical results are conditional.

**Read and apply the topology:**
- `npu-smi info -t topo`: UB means the same HCCS domain; SYS means a PCIe/NUMA crossing.
- One same-domain group: USP4 **bulk** was best in the source observation, with the least communication busy time.
- A cross-domain group: **head-parallel** was better in the observed combination, with faster rank-0 clean-window timing.

**Caveat:** compile × head-parallel was incompatible in this setting; Dynamo's `recompile_limit` caused a silent fallback to eager execution.

## Unlocking parallel strategies under memory constraints

A better parallel strategy may exceed single-card memory. Proceed in two stages:

1. **Try lossless offload features first** to reduce memory and make the strategy feasible: `--enable-cpu-offload`, `--enable-layerwise-offload`, or `--enable-distributed-layerwise-offload`. Check exclusions and side effects. Some framework/model configurations reject all offload; **ordinary layerwise offload triggers the OOM killer on some generations**, so use DLO there. **DLO's no-AllGather path was substantially slower** in the source setting; select its AllGather path.

2. **After lossy changes such as quantization, revisit communication combinations previously blocked by memory.** Reduced memory can unlock new parallelism. For each completed quantization configuration, rerun quick candidate checks over parallel strategy × memory headroom.

## Few-step, multi-rank validation protocol

Few-step multi-rank runs can predict full-step parallel rankings only when the following gates hold.

**Required measurement scope:** compare only the DiT denoising stage: `<Pipeline>.diffuse` wall time, with one row per rank and the minimum taken across ranks. Exclude VAE decoding, text encoding, weight loading and warmup; their fixed-cost variation can exceed the parallelism difference.

**Criterion:** `r = DiT per-step time (anchor configuration) / DiT per-step time (few-step configuration)`.
- `|r−1| ≤ 5%`, dispersion in each cell `≤ 3%`, and matching rankings across both configurations allow extrapolating the few-step ranking.
- If rankings reverse, use the anchor configuration or a higher step count.
- If any cell's dispersion exceeds 3%, the criterion does not hold; resolve noise first.

**Revalidate at a higher step count** after a ranking reversal, per-step drift beyond the threshold, a change in the non-overlapped communication fraction, combined features that alter per-step structure, or a memory-saving change that alters the feasible parallel search space.

## Attributing differences between parallel strategies

### Decompose the stage delta

Compare the two arms row by row in `step_trace_time.csv`, matching column names exactly:

| Column | Meaning |
|---|---|
| `Computing` | Total AI-core timeline duration on the compute stream |
| `Communication(Not Overlapped)` | Exposed communication on the critical path |
| `Overlapped` | Communication already overlapping computation |
| `Stage` | Step wall time |

**Interpretation order:**
1. Inspect `ΔComm(not overlapped)` and `ΔFree` first: these directly carry the timing difference.
2. Inspect `ΔComputing`: extra computation introduced by the strategy's plumbing is not hidden.
3. A change in `ΔOverlapped` without a change in `ΔStage` means communication volume changed while exposure did not; overlap is saturated.
4. **Prefer fractions to absolute savings:** overlap fraction = `Overlapped / Communication`. A high fraction limits the remaining benefit from reducing that communication.

### Cost rule for small collectives

Do not extrapolate small rendezvous-style collectives by byte count. Measure the **WAIT they impose on other streams**. An isolated microbenchmark supplies only a lower bound; measure the real cost inside the pipeline on the target topology.

**Rule:** a small collective's critical-path cost is at least its own duration and increases with rank count and arrival skew. Judge it by waiting time, not bytes.

### Scaling from 4 to 8 cards

Adding cards changes communication volume, communication steps and dependencies. Assess linearity using all of:

- Scaling of communication and computation
- Amdahl's law and synchronization points
- Topology and bandwidth changes

Do not present a comparison across different card counts as a comparison of parallel strategies alone.

## Limits

- MindIE-SD / MiniMax-H3 specifics: this guidance was distilled for diffusion DiT × sequence parallelism. Recalibrate criteria when the model architecture changes.
- Check framework support: if the target framework has no communication-stream mechanism and monkey-patching is infeasible, the work is framework integration.
- No local NPU validation: every threshold and constant depends on hardware, topology and stack version. Remeasure locally when transferring the procedure.

## Maintenance

Update this skill through its review process when a new parallel strategy is validated, the multi-card interconnect topology changes, or a new distributed-training pitfall or CANN defect is discovered.
