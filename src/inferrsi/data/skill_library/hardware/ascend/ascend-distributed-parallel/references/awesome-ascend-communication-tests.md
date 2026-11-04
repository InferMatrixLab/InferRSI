# Ascend communication-test acceptance

Source: [awesome-ascend-skills](https://github.com/ascend-ai-coding/awesome-ascend-skills/tree/75ec89ce9d401be8ac95980e1c3f42f8d4315057)
at `75ec89ce9d401be8ac95980e1c3f42f8d4315057`, inspected 2026-10-23.
**C** denotes directly read wrapper code, **D** a deduction from it, and **P**
a proposed decision/check. The native HCCL test binaries, TorchNPU process-group
implementation and transport algorithms were not read. These are candidate
test-selection and evidence rules, not backend qualification.

License: [README.md:727-749](https://github.com/ascend-ai-coding/awesome-ascend-skills/blob/75ec89ce9d401be8ac95980e1c3f42f8d4315057/README.md#L727-L749)
declares MIT, copyright 2024 Ascend AI Coding. This note is newly authored and
copies no implementation. The separate imported cannbot KV material declares
`license: UNKNOWN`; that declaration is not replaced by the outer README.

## Select and interpret a test

1. **P: Fix the question and effective test stack.** For a native-tool question,
   the inspected quick verifier launches installed `hccl_test` binaries through
   MPI. For a PyTorch integration question, the Python benchmark selects the
   local NPU, initializes an HCCL process group and calls `torch.distributed`.
   Record binary/script revision, PyTorch/TorchNPU/CANN/MPI versions, operation,
   reduction, global/group/local ranks, device mapping, topology, dtype and shape.
   A wrapper source pin does not pin its installed native executable. Reuse the
   owner's card-group and device-health gates before any authorized run.
2. **C/P: Match the actual tensor allocation to the application's payload.** Let
   `S = product(shape) × element_size` and `n` be the group size. In this Python
   script, `all_gather` allocates input `shape` and output `[n × shape[0], ...]`;
   `reduce_scatter` allocates input `[n × shape[0], ...]` and output `shape`.
   Equal CLI shapes therefore do not mean equal input bytes across operations.
   The documented equal-split `all_to_all` case requires the first dimension
   divisible by `n`. Retain both input/output bytes, rather than comparing a
   single displayed size without its meaning.
3. **C/P: Separate completed-call latency from overlap.** Tensors are allocated
   before warmup. Each timed iteration synchronizes the NPU before starting a
   host timer, calls the operation, waits on a returned async work handle when
   applicable, then synchronizes before stopping the timer. `--async-op` thus
   measures a completed, serialized iteration; it does not demonstrate overlap
   with independent computation. The reported percentiles come from one reporting
   rank's local samples, not an all-rank maximum or an application step.
4. **C/P: Audit correctness coverage independently of timing.** The Python
   `--check` path is a separate known-value call after timing. Its scope is:

   | Operation | Actual check at this pin | Acceptance boundary |
   |---|---|---|
   | `all_reduce` | Rank-tagged constant input, expected sum `1 + ... + n` | Expected value is SUM even when another `--reduce-op` is selected; not a valid oracle for PROD/MIN/MAX. |
   | `all_gather` | Rank-tagged constant chunks, expected tags `1, ..., n` | Assumes world-rank tags agree with contiguous group positions. |
   | `broadcast` | Constant 42 from the selected global source rank | Covers that simple pattern only; require source membership and matching buffers. |
   | `reduce_scatter`, `all_to_all`, `reduce`, `send_recv` | Validator falls through to `True` | A printed PASS does not mean values were checked. |
   | `barrier` | Check path is skipped | Connectivity/synchronization observation, not data correctness. |

   The three numerical branches use `allclose` with `atol=1.0`; they are not
   byte-exact or model-quality checks. P: name the actually checked pattern and
   tolerance, and require a separate application-matched oracle for uncovered
   operations, reductions, layouts and rank maps. Do not convert an untested
   case into PASS because its timer or process completed.
5. **C/P: Keep metric provenance and every attempted case.** The Python script
   derives bandwidth from `S`, local mean elapsed time and operation-specific
   factors; e.g. all-reduce bus bandwidth is `2(n-1)S/(n t)`. Reduce-scatter's
   bandwidth calculation uses its output-sized `S`, while its input has `nS`
   bytes. These formula-derived fields are not measured physical link counters
   or proof of the backend's chosen algorithm. The native quick wrapper accepts
   a zero process status plus a `success` or `NULL` text marker; its parser
   assumes four leading fields and averages bandwidth across matched sizes.
   Preserve raw status/logs, per-size rows and numerical-check evidence. A
   mixed-size average or maximum does not establish workload-matched bandwidth.

## Counterexamples and recovery boundary

- **D: Non-prefix subgroup check.** In group `[1, 3]`, the SUM validator seeds
  global-rank tags 2 and 4 but expects `1 + 2 = 3`. This mismatch concerns the
  wrapper's reference calculation; it is not evidence that HCCL SUM is wrong.
  Establish a group-aware oracle before interpreting that failure.
- **D: P2P schedule.** The four-rank `send_recv` code sets each peer to
  `(global_rank + 1) % group_size`: rank 0 sends to 1 while rank 1 waits for 2.
  That schedule is not reciprocal. Do not reuse the advertised multi-rank case
  as a pipeline-parallel test until the peer map and matching sends/receives are
  established; no hang was reproduced here.
- **C: Runner side effects.** The native quick wrapper kills processes by broad
  name patterns before tests. It is not an automatic preflight for a shared
  host. Any later execution needs an authorized, isolated allocation and cleanup
  limited to the caller's owned processes; this skill supplies no runner.
- **P: Stop on missing coverage or setup failures.** Separate missing binaries,
  launch/mapping errors, unsupported cases and failed numerical checks. Retain
  each attempted case and its raw evidence; do not infer a transport failure
  from a wrapper oracle mismatch or grant unsupported operations a pass.

## Proposed verification

P: With separate execution authorization, begin with a matched default-world
SUM case and explicit floating dtype. Freeze warmup/iteration counts, message
bytes, rank/device mapping and topology. Check results on every participating
rank, then use reciprocal P2P and group-aware references before extending to
those cases. Record setup, completed-call latency and numerical outcomes
separately. Use a real producer/consumer timeline to test overlap and an
application workload to test end-to-end benefit. None was run in this extraction.

## Exact source map

| Rule | Pinned source and inspected lines | Evidence kind |
|---|---|---|
| MPI/native entry, installed binary and launch size | [quick-verify.sh:10-16,125-158,174-195](https://github.com/ascend-ai-coding/awesome-ascend-skills/blob/75ec89ce9d401be8ac95980e1c3f42f8d4315057/skills/training/hccl-test/scripts/quick-verify.sh#L10-L195) | C: wrapper only; native binary uninspected |
| Native success heuristic and cleanup | [quick-verify.sh:140-165](https://github.com/ascend-ai-coding/awesome-ascend-skills/blob/75ec89ce9d401be8ac95980e1c3f42f8d4315057/skills/training/hccl-test/scripts/quick-verify.sh#L140-L165) | C: raw status/text and process-name cleanup |
| Parser schema and size summaries | [parse-hccl-result.py:16-30,42-62](https://github.com/ascend-ai-coding/awesome-ascend-skills/blob/75ec89ce9d401be8ac95980e1c3f42f8d4315057/skills/training/hccl-test/scripts/parse-hccl-result.py#L16-L62) | C: four-field regex and arithmetic summary, not native-format qualification |
| Tensor bytes/shapes and bandwidth formulas | [comm-bench.py:53-95,106-139](https://github.com/ascend-ai-coding/awesome-ascend-skills/blob/75ec89ce9d401be8ac95980e1c3f42f8d4315057/skills/training/torch-npu-comm-test/scripts/comm-bench.py#L53-L139), [supported-ops.md:49-58,81-89,143-152](https://github.com/ascend-ai-coding/awesome-ascend-skills/blob/75ec89ce9d401be8ac95980e1c3f42f8d4315057/skills/training/torch-npu-comm-test/references/supported-ops.md#L49-L152) | C plus source documentation; no backend algorithm audit |
| Dispatch, P2P peer calculation and oracle | [comm-bench.py:142-240](https://github.com/ascend-ai-coding/awesome-ascend-skills/blob/75ec89ce9d401be8ac95980e1c3f42f8d4315057/skills/training/torch-npu-comm-test/scripts/comm-bench.py#L142-L240) | C; subgroup/P2P counterexamples are D |
| Group setup, timing and reporting | [comm-bench.py:243-366](https://github.com/ascend-ai-coding/awesome-ascend-skills/blob/75ec89ce9d401be8ac95980e1c3f42f8d4315057/skills/training/torch-npu-comm-test/scripts/comm-bench.py#L243-L366) | C: global rank retained with group size; per-rank reporting |
| CLI options | [comm-bench.py:369-408](https://github.com/ascend-ai-coding/awesome-ascend-skills/blob/75ec89ce9d401be8ac95980e1c3f42f8d4315057/skills/training/torch-npu-comm-test/scripts/comm-bench.py#L369-L408) | C: accepted flags do not establish working backend combinations |

Status remains candidate; backend/runtime and agent efficacy are **not_run**.
No source script was executed, no dependency installed, and no claim is made
about implementation correctness, physical transport, NPU compatibility or gains.
