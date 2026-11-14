# NInfer state-restoration and completion contracts

Use this reference to freeze a validation plan or audit a supplied hybrid speculative-decoding report. It identifies the state, counts and completion observations a comparison needs. The [source record](ninfer-source.json) fixes NInfer's identity, exact readset and rights. This is candidate knowledge; native correctness, model quality, performance and agent efficacy are unverified.

The inspected implementation slice is Qwen3.5 GDN/MTP, with an eager producer-to-fold path and the source's public checkpoint and execution contracts. KDA/GLM, DFlash probability math, distributed/Spark behavior and current Graph/kernel qualification are outside this slice. A historical CUDA Graph campaign is a separate author-reported measurement, not evidence that this current implementation was run.

## Freeze the object being compared

Record source/build and model/artifact revisions, speculative backend, draft and physical verify widths, sampling/output policy, state and record geometry, dtypes, actual execution path and checkpoint identity. Keep these objects distinct:

| Object or count | Meaning in the selected source |
|---|---|
| Main frontier `F` | Main has executed inputs `[0,F)`; the known next input can remain an unexecuted anchor |
| MTP history frontier | Stable history reaches `max(F-1,0)` and uses true Main conditioning, not recursive draft hidden |
| Complete checkpoint | Position-related StateImage, appropriate Main/backend histories and their continuation/coverage metadata |
| `accepted_drafts` | Draft positions accepted by target verification; this alone does not state the final adopted prefix |
| Licensed output prefix | Candidate outputs that the frontend may inspect for EOS, stop, budget, grammar failure or cancellation |
| `CommitDecision.accepted_tokens` | Frontend-adopted output extent, which drives the corresponding committed input extent |
| Committed versus accepted draft counters | Adopted draft work and verification acceptance are recorded separately |

A round adopting `N` outputs commits the corresponding `N` inputs; the last new output becomes the next anchor. Zero accepted drafts can still leave a target-only output to adopt. It must not be used as a zero-state-update control. Cancellation or constraint failure instead requires a terminal decision with zero adopted tokens in the inspected Session contract.

The [speculative contract](https://github.com/Neroued/ninfer/blob/1882c6adbc98043fcf89f3589aa5addb3742777a/docs/maintainer/speculative-decoding.md#L6-L44) states the alignment. [Session commit](https://github.com/Neroued/ninfer/blob/1882c6adbc98043fcf89f3589aa5addb3742777a/src/models/qwen3_5/session/commit.cpp#L203-L321) validates final decisions and records the distinct counters. These are source observations, not executed parity results.

## Establish a coupled restore point

Identify the StateImage's convolution history, FP32 recurrent state and continuation hidden, plus Main/MTP histories and their frontiers. Freeze their common provenance and valid coverage before selecting a reference run. The inspected binding path prepares both histories, transfers or adopts the state image, restores continuation metadata and reconstructs sampling counts from the committed ledger when required.

Matching tokens or a prefix digest does not prove that independently recomputed State and KV form one valid checkpoint. Trimming KV alone cannot recover an earlier recurrent state. Preserve model/position/media identity and distinguish logical content from its movable address and from an active consumer's storage lease. A restored replay frontier is also distinct from the first genuinely new unit of work.

Read the [Context contract](https://github.com/Neroued/ninfer/blob/1882c6adbc98043fcf89f3589aa5addb3742777a/docs/maintainer/context-management.md#L27-L77), selected [StateImage layout](https://github.com/Neroued/ninfer/blob/1882c6adbc98043fcf89f3589aa5addb3742777a/src/models/qwen3_5/state/state_image.cpp#L7-L18) and [binding functions](https://github.com/Neroued/ninfer/blob/1882c6adbc98043fcf89f3589aa5addb3742777a/src/models/qwen3_5/session/binding.cpp#L158-L399) for this source boundary. They do not qualify arbitrary checkpoint combinations or another model's state representation.

## Select the same-block state oracle

For an authorized native comparison, begin from one initial state and one complete physical verify block. Retain the represented convolution/key/value/gate records actually consumed during that block. Compare a fold of `[0,m)` against the corresponding snapshot in the recurrence trajectory of that **same full block**. Re-running projection at width `m` can change finite-precision evaluation and is a different oracle.

The [GDN fold contract](https://github.com/Neroued/ninfer/blob/1882c6adbc98043fcf89f3589aa5addb3742777a/include/ninfer/ops/gdn_replay.h#L19-L49) specifies FP32 recurrence and the last three time positions per convolution channel from old history plus the adopted records. It requires identity with the matching same-block snapshot, stable physical record-row identity, disjoint active destinations and preserved operands through their last consumer. This is an intended numerical contract, not a numerical result obtained here.

The eager producer explicitly selects `ReplayRecords`, records the convolution transition and represented recurrent inputs, and the commit composition folds the chosen prefix. MTP history is then rebuilt from true Main hidden features as needed. Accepting a token does not make recursive draft hidden equivalent to Main hidden, so truncating the draft cache is not a substitute for that repair. Exact producer/consumer anchors are in the source record.

The inspected [fold test sections](https://github.com/Neroued/ninfer/blob/1882c6adbc98043fcf89f3589aa5addb3742777a/tests/ops/linear_attention/gated_delta_net/test_fold.cpp#L330-L565) define same-block snapshots, byte comparisons and record/source/guard preservation. Their registered cases include zero, mixed and full prefix lengths, with in-place and separate destinations. These are unexecuted source assertions. Future native results must name the actual source build, geometry and executing route; a source read, host declaration or skipped case is not a pass.

## Freeze negative controls and their observations

| Control selected before the comparison | Required observation and interpretation |
|---|---|
| No draft position accepted, ordinary target output adopted | Keep `accepted_drafts`, licensed extent and final adopted extent separate; do not expect a zero-state update merely from draft rejection |
| Zero adopted input, including a cancelled terminal row | The GDN fold contract permits no state/record access for a zero row; no adopted prefix is published. Other rows and asynchronous retirement remain separate observations |
| Mixed zero/partial/full rows | Preserve physical row identity; inspect each row's own source, destination and adopted extent instead of compressing the active rows |
| EOS, stop or output budget cuts a licensed prefix | Commit/fold the frontend's final extent and preserve termination reason; rejected or unadopted suffix bytes are not recoverable history |
| Separate source and destination | Check the selected state, source preservation, record immutability and untouched guards; compare the next-use state/logits only under a justified numerical/sampling contract |
| Cancellation while work is in flight | Correlate the actual boundary snapshot and final decision with the same execution ticket; cancellation is not evidence that GPU work or transfers have completed |

These are proposed validation observations derived from source contracts. They do not introduce test implementations or a universal tolerance. Keep the original native operator/model package and real dependencies when a future check is authorized. Do not replace the source with an extracted formula, mock or a CPU substitute for the required CUDA execution.

On the first mismatch, retain the initial checkpoint and block identity, first differing row/layer/frontier, represented inputs, final decision and execution identities. Withhold a native state-correctness conclusion while any required oracle, checkpoint identity or receipt is missing. Under stochastic sampling, state-contract checks do not by themselves justify token-for-token equality between runs consuming different random draws.

## Correlate adoption, publication and retirement

The selected frontend previews an allowed prefix, Session accepts the model commit and adopts its logical result, and only then does the frontend commit and publish its preview. A commit failure must not become a published token without model state. [The complete runtime function](https://github.com/Neroued/ninfer/blob/1882c6adbc98043fcf89f3589aa5addb3742777a/src/runtime/engine/engine_execution.inl#L5-L241) exposes that order.

Record the session epoch, sequence/residency generation, frame generation, execution ticket and final command where available. `ResultReady`, `CommitReceipt` and `DeviceRetired` denote different facts. The local executor returns a receipt while the flight is retiring; it releases the frame only after checked retirement for the final command. Session then completes/publishes its pending context transactions and clears cancelled or discarded lanes. The ledger points to each corresponding function.

A cancel flag, host return or recorded event alone cannot establish storage reuse. Conversely, logical adoption need not wait for host synchronization of every device consumer. Preserve the source's ordering rather than adding a guessed global synchronization to the benchmark. Missing correlation or retirement evidence leaves cancellation/reuse behavior unverified.

## Interpret historical completion denominators

The inspected [methodology](https://github.com/Neroued/ninfer/blob/1882c6adbc98043fcf89f3589aa5addb3742777a/docs/performance/methodology.md) and [Qwen3.8 report](https://github.com/Neroued/ninfer/blob/1882c6adbc98043fcf89f3589aa5addb3742777a/docs/performance/qwen3.8-27b.md) describe September 28–29, 2026 author runs at `7f6aafedb5f20200def820cfe51ab81c09c20eeb`. They used one RTX 5090 32 GiB, driver 617.14, CUDA 13.4, FP8 E4M3 row-256 KV, chunk 1,024, disabled prefix reuse and the recorded model/artifact/backend settings. They are not measurements of the source revision used for this reference. Raw report directories are identified in the source page but were not available in this readset.

| Published quantity | Boundary to preserve |
|---|---|
| Per-request decode phase | Completion tokens minus the first prefill-produced token, divided by that request's decode time |
| Complete corpus decode | Sum of decode tokens divided by the entire 75-request makespan, including prefill, admission waits, transitions and drain |
| Selected steady decode | Committed decode tokens over eligible complete full-batch intervals; excludes ramp-up, prefill, recovery and drain |
| Acceptance | Phase tables average per-request ratios; corpus/wave tables divide summed accepted drafts by summed drafted tokens |
| Termination and task success | Stop token, output limit, request/CUDA error and quality score are separate outcomes |

For example, the reported NVFP4 C=8 steady wave is 922.4 tok/s, while its full-corpus rate is 490.9 tok/s. Their denominators and workloads differ; taking their ratio does not establish a speedup. Each saturation point is one wave, not a repeated-sample mean.

All 820 formal requests were reported free of request/CUDA/allocation errors, but this does not establish task completion. The C=1 NVFP4 MTP3 corpus retains 40 stop-token and 35 output-limit outcomes among 75; all five AIME 15 samples reach 65,536 output tokens. The campaign did not measure answer accuracy, prompt compliance or perplexity. Separate model-card scores are not a same-run quality gate. Preserve all samples and report missing quality coverage rather than converting a token budget or natural stop into task success.

## Route to the existing responsibility

- For verification-row allocation from acceptance and a cost model, use [budget-speculative-verification](../../../repositories/deepinfer/budget-speculative-verification/SKILL.md). It budgets verification; it does not supply this GDN restore oracle.
- For Ouro LAST_EXITED depth-plane KV propagation and contiguous written-history checks, use [audit-recurrent-kv-finalization](../../../repositories/vllm-rlt/audit-recurrent-kv-finalization/SKILL.md). Its scoped synchronous path excludes speculation/preemption; it is not a replacement for this source's StateImage/frontier contract.
- Use this reference to produce a frozen validation plan or source-bound report interpretation. Model/device parity, quality, repeated performance and service acceptance require separately authorized native evidence and frozen campaign gates.

## Rights and evidence boundary

The selected NInfer software/documentation uses Apache-2.0; its exact license identity and selected-file checks are in the source record. This reference uses original procedural prose and attribution, with no copied implementation, model weights, fixture corpus, figure or vendored dependency. NInfer explicitly separates model and vendor licenses from its software license. The selected readset is not a whole-tree or model-weight license audit.
