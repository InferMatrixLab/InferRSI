# HCCL multi-rank AllReduce: selection, scratch and completion

Status: **candidate**; empirical validation: **not_run**. The
[source readset](hccl-allreduce-readset.json) records official `cann/hccl` commit
`96fab0a2acb761e7f8ab0f94aeb5138f200a345b`, its tree, exact inspected ranges,
Git blobs and full-file SHA-256/byte counts. Acquisition was a direct shallow
clone from [the official GitCode repository](https://gitcode.com/cann/hccl).
Hashing a complete file does not imply inspecting every function in it. The
[upstream license](hccl-LICENSE.md) is retained without replacing the inherited
wrapper/strategy provenance or resolving its license uncertainty.

**CODE** identifies selected implementation; **TEST** identifies inspected test
definitions, not a test result; **INFERENCE** is a consequence of that code;
**PROPOSED** is a validation or decision rule. No HCCL build, simulator test,
NPU execution, native numerical check or performance experiment was run.

## Entry and algorithm selection

The bounded path is positive-count, multi-rank OPBASE AllReduce, with the final
algorithm `AicpuAllReduceSoleMeshOneShot` and AICPU task-cache replay disabled.
It stops at HCOMM/ACL calls. It does not establish the installed framework's
dispatch, the HCOMM transport implementation or behavior on another CANN build.

| Stage | Observed source behavior | Decision and boundary |
| --- | --- | --- |
| Open implementation entry | **CODE:** S1 sends HCOMM versions below `9.0.0` or devices failing `IsOutPlaceDevice` to other implementations. S2 recognizes the `DEV_TYPE_950` and `DEV_TYPE_960` enums. Zero count returns early; rank one reaches `SingleRankProc` before selection. | **PROPOSED:** establish the loaded HCCL/HCOMM builds, device enum, positive count and communicator rank count. A successful empty or rank-one call cannot qualify this multi-rank path. The enum gate is not validation of either product or a legacy device route. |
| Topology and selector route | **CODE:** S3 obtains topology and routes `MESH_1D`, or `IsDevType960()`, through `SelectorEngine`; other cases use `ExecuteSelector`. A compiled/loaded algorithm plugin can return before either route. | **PROPOSED:** capture actual topology, engine configuration and final algorithm. Card count or an environment variable alone does not identify the implementation. This reference follows ordinary `MESH_1D` without a plugin override. |
| Cost-based selection | **CODE:** S4 initializes/reuses a cost model, generates a cost table, permits tuner modification, then selects a minimum-cost entry. S5 filters topology, missing executors and empty cost coefficients. Preferred algorithms can fail topology filtering. S6's one-shot cost function returns no coefficients above eight ranks. | **INFERENCE:** one-shot eligibility is narrower than an API accepting the rank count, and eligibility does not guarantee selection or measured speed. A cost value is a model output, not a measured latency from this extraction. Complete cost/op filters and tuner internals are outside scope. |
| Topology match and registration | **CODE:** S7 registers the one-shot name with `InsV2AllReduceSoleExecutor`, `TopoMatchOneLevel` and `InsTempAllReduceMesh1DOneShot`; its attributes declare one topology level and full mesh connectivity. S8 requires an engine-compatible physical level whose local rank list covers the full communicator. | **PROPOSED:** retain both communicator ranks and physical device mapping. Do not equate contiguous device IDs, one server, or a two/four/eight-card convention with a qualified mesh. Other registered topology shapes are not covered by this walkthrough. |
| Final execution | **CODE:** S3 can reuse a cached fallback or retry after unavailable resources, then resolves the final executor and launches AICPU. S9's cache-disabled V2 entry calls `OpOrchestrate`, which resolves the algorithm and calls `executor->Orchestrate`. | **PROPOSED:** verify the final algorithm/engine and cache state after fallback. Initial selection logging alone is insufficient; plugin, cache replay, AIV, CCU, DPU and legacy paths need separate qualification. |

**Counter-signal to a size-only rule:** S10 contains an `8 * 1024 * 1024` byte
one-shot heuristic in `AllReduceAutoSelector::SelectMeshAlgoAicpu`. S3 routes the
ordinary `MESH_1D` entry through the cost selector instead. That constant, and
the similarly named test constants, are source facts about particular branches,
not universal tuning thresholds or proof that a small call ran one-shot.

## Multi-rank data and synchronization path

**CODE (S6-S7, S11):** let `r` be the template rank count, `C` the available HCCL
scratch-buffer bytes and `d` the element size. The template requests `r` threads
including the main thread and a scratch multiplier of `r`. In the selected
AICPU path without symmetric-memory bypass, the executor computes a per-loop
byte ceiling from `floor(C / r / a) * a`, bounded by its transport ceiling,
where this pin defines alignment `a = 128`. It converts that ceiling to an
element count, rejects a zero count, iterates over the payload and handles the
last partial chunk. The template lays out one full chunk-sized slot per rank.
This is HCCL scratch accounting; it is not a host-RAM budget or a total device
memory measurement.

For each chunk, the selected template does the following:

1. **CODE:** check that thread count equals template rank count and enqueue
   main-to-subthread notifications. Copy this rank's input into its local scratch
   slot. The single-rank copy branch exists but is not the inspected multi-rank
   mechanism.
2. **CODE:** for every other rank, use a separate subthread and its peer channel
   to write this rank's full input chunk into the corresponding sender slot in
   the peer's HCCL buffer. This is an all-peer exchange, not a ring
   reduce-scatter/all-gather implementation.
3. **CODE (S12):** `SendRecvBatchWrite` delegates to a batch-transfer wrapper,
   or `SendRecvWrite` when the HCOMM batch capability is absent. Both enqueue
   peer-buffer readiness acknowledgement, writes and data-ready notifications
   with a matching wait. The fallback calls `HcommWriteOnThread`; the batch
   path calls `HcclHcommBatchTransferOnThread`. Physical transport behavior
   below those APIs was not inspected.
4. **CODE:** enqueue subthread-to-main completion synchronization, then reduce
   scratch slots `1..r-1` into slot zero and copy slot zero to the user output.
   S12 maps ordinary local reduction to `HcommLocalReduceOnThread`. The template
   adds batch-mode/thread joins for `INT64`, `UINT64`, `FP64` or `PROD`, and the
   wrapper uses a distinct `AicpuReduce` path; those reduction internals are
   excluded from this extraction.

**INFERENCE:** per chunk, each rank supplies its full chunk to `r-1` peers and
performs `r-1` local reductions after synchronization. Increasing ranks can
increase scratch demand, peer work and local reduction work even with the same
application payload. A generic ring-derived bus-bandwidth formula does not
measure this implementation's physical link traffic. HCCL enqueue success and
thread notifications are also distinct from a host observer waiting for the
terminal stream/event before reading output or elapsed time.

**CODE, bounded error-propagation observation (S6, S16):** `KernelRun` wraps
`PostLocalReduce` in `CHK_PRT` and then returns `HCCL_SUCCESS`. At this pin,
`CHK_PRT` logs a failed result without returning it, unlike `CHK_RET`. Thus a
failure returned by `PostLocalReduce` is not propagated through this particular
`KernelRun` return. This is a static call-site observation, not an injected or
reproduced NPU failure, nor a claim that other runtime error reporting cannot
detect it. **PROPOSED:** retain error logs and completed-output checks alongside
API status; qualify failure reporting separately before relying on it.

## What the upstream tests actually check

**TEST (S13):** `RunAllReduceCase` creates a `SimWorld` with `DEV_TYPE_950`, sets
`HCCL_OP_EXPANSION_MODE=AI_CPU`, launches one host thread per rank, marks simulated
input/output allocations, calls `HcclAllReduce`, joins the threads, and passes
the collected task queues to `CheckAllReduce`. It does not initialize real NPU
tensors and compare floating-point values on hardware.

The six `st_all_reduce_1shot_*` definitions cover two-rank FP16/MAX at the source
size boundary, two-rank BF16/SUM nearby, three-rank INT16/MIN with count one,
four-rank INT32/SUM with an odd count, eight-rank FP32/MIN and seven-rank INT8/MAX.
The neighboring `st_all_reduce_2shot_lower_boundary_data` definition uses a
larger count. These are useful case inputs; their names do not establish final
algorithm selection. The inspected runner contains no assertion that the final
algorithm is `AicpuAllReduceSoleMeshOneShot`.

**TEST (S14-S15):** `CheckAllReduce` constructs a graph/operation-semantics
checker. The selected AllReduce semantic checker requires contiguous output
coverage, all ranks' input provenance, matching source offsets and the expected
reduction type, including the tail. This is structural semantic coverage. It
does not qualify numeric rounding, deterministic reduction, native timeout or
transport behavior, bandwidth, memory pressure or application quality. The
surrounding simulator and graph-checker implementation were not fully audited.

## Counter-signals and discriminating checks

All checks below are **PROPOSED**; none is a reproduced native failure.

| Tempting conclusion | Counter-signal | Discriminating check |
| --- | --- | --- |
| A successful smoke call validates communication | Count is zero, rank count is one, or a compatibility entry was used | Capture nonzero bytes, more than one participating rank, device/build identity and final native algorithm |
| A selected environment option proves one-shot ran | Cost filtering, tuner/plugin selection or cached/resource fallback changes the path | Retain final algorithm/engine plus per-rank trace and fallback/cache diagnostics for each size |
| More ranks must reduce collective latency | This one-shot path adds peer writes, local reductions and rank-scaled scratch; scratch limits can increase loop count | Compare matched message sizes with scratch/loop observations, all-rank completed-call timings and a timeline |
| A test called `1shot` validates this algorithm | The simulator calls the general API and does not assert the selected name | Confirm its dispatch when running the simulator; separately exercise the native selected path with an independent numerical oracle |
| A communication-test PASS proves SUM, PROD and arbitrary groups | The retained wrapper has operation/subgroup oracle limits; the simulator tracks semantics, not numerical tensors | Use rank- and position-distinct inputs, an operation-correct reference and checks on every communicator rank |
| An API success return proves local reduction succeeded | The inspected `KernelRun` logs rather than propagates a `PostLocalReduce` error at that call site | Keep logs, terminal completion and independent output checks; test error reporting separately in an isolated authorized harness |
| Lower enqueue time or reported bus bandwidth proves overlap | Work may still be pending; a formula-derived metric can assume a different algorithm | Wait for completion, separate enqueue from completed latency, and inspect producer/communication/consumer dependencies in the application trace |
| Replacing the peer/thread waits is harmless | The local reductions consume scratch written by other ranks | Preserve the dependency graph; validate tail chunks, repeated reuse and arrival skew before interpreting any timing difference |

## Target validation recipe (not run)

1. Freeze HCCL/HCOMM builds and revisions, CANN/ACL runtime, driver/firmware,
   device generation, communicator-to-device map, topology, engine/algorithm
   settings, loaded plugins/tuner, task-cache state, scratch size, count, dtype,
   reduction and stream mode. The source pin does not identify the installed
   binary. Start within the positive-count, multi-rank OPBASE route above;
   inspect legacy or alternate paths separately when the gate fails.
2. In the prepared upstream build, run the selected simulator case definitions
   with their actual invocation and per-case results retained. Confirm which
   algorithm each case selected. Treat a simulator pass as task-graph evidence,
   not a hardware result. No build command or simulator binary was executed here.
3. For the target NPU harness, initialize each rank's input with distinct rank
   and position values and retain an independent all-rank reduction reference.
   Begin with a supported ordinary dtype/SUM pair, then cover the application's
   dtype/op and count variants. Check every output on every rank after terminal
   stream/event completion. Freeze tolerances/determinism requirements before
   comparing floating reductions; byte identity is not a universal SUM oracle.
4. Include count one, odd counts, the final partial chunk, values on both sides
   of the observed scratch-loop and dispatch transitions, repeated buffer reuse
   and application rank maps. Keep an empty and rank-one control explicitly
   separate. Only test other rank/topology combinations that the target supports;
   the simulator's odd-rank cases do not establish native topology support.
5. After correctness, measure preparation/resource acquisition, host enqueue,
   completed collective latency and the application stage separately. Preserve
   every rank's samples and the slowest participating rank for completion-cost
   interpretation, including cold/warm cache and fallback differences. Log the
   selected algorithm and loop count for each point; retain regressions and
   unsupported/failed cases. Compare overlap only with a producer/consumer
   timeline and controlled arrival skew.
6. Keep operator/simulator evidence separate from model quality and service
   evidence. Run the authorized application validation with frozen controls
   before claiming a parallelism or service gain. Missing native or application
   evidence remains **INCONCLUSIVE** for those claims; source inspection and
   package-reader checks do not promote this candidate.

## Precise source map

All links resolve under the same immutable official source commit. The readset
also supplies each full-file identity; listed ranges bound these observations.

| ID | Pinned source and inspected evidence |
| --- | --- |
| S1 | [all_reduce.cc:23-56,194-269,305-314](https://gitcode.com/cann/hccl/blob/96fab0a2acb761e7f8ab0f94aeb5138f200a345b/src/ops/all_reduce/all_reduce.cc#L23-L56): API gates, multi-rank selection/execution, OPBASE wrapper |
| S2 | [hccl_common.h:333-354](https://gitcode.com/cann/hccl/blob/96fab0a2acb761e7f8ab0f94aeb5138f200a345b/src/common/hccl_common.h#L333-L354): open-device enum gate |
| S3 | [op_common.cc:93-148,160-200,987-1086,1093-1115,1222-1238,1310-1392](https://gitcode.com/cann/hccl/blob/96fab0a2acb761e7f8ab0f94aeb5138f200a345b/src/ops/op_common/op_common.cc#L160-L200): plugin/topology routing, fallback, executor, resource and AICPU launch calls |
| S4 | [selector_engine.cc:388-456,572-659](https://gitcode.com/cann/hccl/blob/96fab0a2acb761e7f8ab0f94aeb5138f200a345b/src/ops/op_common/selector/selector_engine.cc#L388-L456): table/tuner/minimum selection |
| S5 | [cost_model.cc:387-444](https://gitcode.com/cann/hccl/blob/96fab0a2acb761e7f8ab0f94aeb5138f200a345b/src/ops/op_common/selector/cost_model.cc#L387-L444): topology/executor coefficient filtering |
| S6 | [ins_temp_all_reduce_mesh_1D_one_shot.cc:23-57,60-138,140-242,244-262](https://gitcode.com/cann/hccl/blob/96fab0a2acb761e7f8ab0f94aeb5138f200a345b/src/ops/all_reduce/algorithm/template/aicpu/ins_temp_all_reduce_mesh_1D_one_shot.cc#L60-L242): rank eligibility, scratch, thread resources, peer writes, joins and local reduction |
| S7 | [ins_v2_all_reduce_sole_executor.cc:80-107,133-298,373-379](https://gitcode.com/cann/hccl/blob/96fab0a2acb761e7f8ab0f94aeb5138f200a345b/src/ops/all_reduce/algorithm/executor/ins_v2_all_reduce_sole_executor.cc#L133-L298): template binding, resource preparation and chunk/tail loop |
| S8 | [topo_match_one_level.cc:23-106](https://gitcode.com/cann/hccl/blob/96fab0a2acb761e7f8ab0f94aeb5138f200a345b/src/ops/op_common/algorithm/topo_match/topo_match_one_level.cc#L23-L106): full-communicator physical-level match |
| S9 | [kernel_launch.cc:276-323,654-730,823-833](https://gitcode.com/cann/hccl/blob/96fab0a2acb761e7f8ab0f94aeb5138f200a345b/src/ops/op_common/algorithm/template/aicpu/kernel_launch.cc#L276-L323): native V2 entry and cache-disabled executor orchestration |
| S10 | [all_reduce_auto_selector.cc:18-35,530-564](https://gitcode.com/cann/hccl/blob/96fab0a2acb761e7f8ab0f94aeb5138f200a345b/src/ops/all_reduce/selector/all_reduce_auto_selector.cc#L530-L564): comparison-only size heuristic |
| S11 | [alg_template_base.h:26-34](https://gitcode.com/cann/hccl/blob/96fab0a2acb761e7f8ab0f94aeb5138f200a345b/src/ops/op_common/algorithm/template/alg_template_base.h#L26-L34): slice-alignment definition |
| S12 | [alg_data_trans_wrapper.cc:157-180,245-270,428-479,880-928,1010-1078](https://gitcode.com/cann/hccl/blob/96fab0a2acb761e7f8ab0f94aeb5138f200a345b/src/ops/op_common/algorithm/template/wrapper/alg_data_trans_wrapper.cc#L428-L479): HCOMM batch/fallback writes, notifications, local copy/reduce |
| S13 | [all_reduce_testcase.cc:11-183](https://gitcode.com/cann/hccl/blob/96fab0a2acb761e7f8ab0f94aeb5138f200a345b/test/st/algorithm/testcase/all_reduce_testcase.cc#L48-L183): simulator runner and selected case definitions |
| S14 | [hccl_verifier.cc:11-24](https://gitcode.com/cann/hccl/blob/96fab0a2acb761e7f8ab0f94aeb5138f200a345b/test/st/algorithm/utils/src/hccl_verifier/hccl_verifier.cc#L11-L24): AllReduce graph-check entry |
| S15 | [allreduce_semantics_checker.cc:18-90](https://gitcode.com/cann/hccl/blob/96fab0a2acb761e7f8ab0f94aeb5138f200a345b/test/st/algorithm/utils/src/hccl_verifier/semantics_check/allreduce_semantics_checker.cc#L18-L90): output/source/reduction semantic coverage |
| S16 | [log.h:200-212,243-254](https://gitcode.com/cann/hccl/blob/96fab0a2acb761e7f8ab0f94aeb5138f200a345b/src/common/log.h#L243-L254): return-on-error versus log-only macro behavior at the selected template call site |

No whole-collective-library, whole-topology, HCOMM, transport, numerical,
determinism or performance qualification follows from this bounded source path.
