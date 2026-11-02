# Final TorchNPU candidate report

## Source and generated graph

Main source: Ascend/pytorch master `046934140b96836c3fcef14d0f39ae54dc0a06bf`; additional exact parent gitlink:
Ascend/op-plugin `ad946817034b3270e309c81c54f0ee808d0b62cb`. Both snapshots clean; no native package installed.
The complete tracked main tree contains 4,453 entries and 492 directories.
Actual semantic readset: 54 files, 75 retained inspected spans across
the two sources. Git blob SHA-256/OID and checkout hashes are distinct.

Runtime: `frameworks/torch-npu/torch-npu`, root plus eight canonical children,
three helpers, 11-gitlink provenance, capability/script inventory, mechanism and
troubleshooting references, five exact license/notice files. AREX source and
license resolver output are retained separately from runtime source evidence.

## Coverage and verification

- Primary route coverage: installation/compatibility, registration/dispatch,
  operator development, memory/streams/events, graphs/compilers, distributed/HCCL,
  training/precision and profiling/debugging.
- Source depth: actual allocator free/event reaping, stream/event queue boundary,
  graph private pools/guards, HCCL producer/communication/consumer lifetime,
  generated registration, AMP and CANN profiling bridge.
- Usability: 19 directories, including two difficult synthetic cases per child,
  root routing and two integrated cases. All 105 static content assertions pass.
  Separate independent agent replay is not claimed here.
- Helper verification: help/default plans, malformed contract/error recovery,
  absent-package classified block and AST parsing. A local helper PASS does not
  validate its unexecuted device branch.
- Native: one original stdlib source-version helper PASS; eight required-backend
  candidates BLOCKED_REQUIRED_BACKEND and not launched after host feasibility
  failure. No NPU operation, HCCL group, AMP numerical case, graph/compiler or
  profiler collection executed locally.
- Source integrity: 54 immutable file digests/OIDs and 75 normalized
  span digests verified. Five retained license/notice digests match Git blobs.
- Destination metadata: native local-skill-v1; AREX structured fields in sidecars.
  The integrator owns a separately labeled scratch-frontmatter license adapter
  report; do not call the native tree an unmodified AREX-frontmatter pass.

## Limits and disposition

This is a source-supported candidate suitable for repository review with exact
backend limits, not a fully backend-verified managed skill. No DisCo import was
performed. Existing allocator-owner source pins remain unchanged. Candidate
and empirical_validation=not_run remain intact. No performance, model-quality,
service or convergence claim is made.

The gap register names inventoried-only ONNX/JIT/serialization internals,
quantized/custom dtypes, per-optimizer algorithms, higher-level sharding/pipeline,
RPC/SHMEM/IPC, specialized compiler passes/FXRT executor and fault/recovery
contracts. op-plugin inspection is representative, not every operator/kernel.
Other gitlinks and external CANN internals remain uninspected.

Remote validation should first qualify the actual Linux/CANN/NPU stack, run
selected upstream import/stream/graph/AMP tests plus a tiny HCCL multi-rank case
and bounded profiler collection, then separately qualify optional compilers or
specialized workloads. Do not upgrade a missing native check to PASS because
the repository packages or static assertions succeed.
