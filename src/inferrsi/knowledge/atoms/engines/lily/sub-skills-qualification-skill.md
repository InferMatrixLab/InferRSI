---
name: qualification
description: "Qualify Lily's exact-checkpoint Rust/Metal inference by separating CPU reference algorithms, executed GPU kernels, shader builds, model goldens and version-bound production-throughput reports. Use for test coverage, route boundaries, numerical changes, benchmark evidence or performance claims."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
---

# Qualify native behavior and benchmark evidence

This route is source-derived candidate guidance. It does not certify Rust
compilation, Metal execution, model quality or performance. Read the
[verification contract](references/verification-contract.md) for test semantics,
measurement boundaries and preserved report limitations; use
[troubleshooting](references/troubleshooting.md) for a misleading green test,
missing pipeline, changed golden or version mismatch.

## Establish the exact tuple

Record source/build and lockfile identities, compiler, macOS and Apple GPU
family, checkpoint revision plus actual weight/tokenizer/template hashes,
quantization layout, numerical settings, prompt/token sequence, sequence and
output budgets, cache state and request workload. Lily's inspected model loader
supports one Qwen3.6-35B-A3B affine-Q4 checkpoint layout, not arbitrary 4-bit
models or a general Qwen family. Route representation/runtime work to
[model-runtime](../model-runtime/SKILL.md).

For comparisons, additionally freeze engine/harness/MLX package versions,
binary/source/harness digests, production versus diagnostic mode, timing
boundaries, warmup/lookahead policy, sample schedule, quality/latency/resource
gates, validators and authorized stop condition before experimentation.

## Procedure

1. **Determine what compiled and executed.** Non-macOS library module gating is
   not a supported CPU inference backend. The plain-Rust CPU reference is a
   numerical oracle used by Metal tests; its library exposure is itself
   macOS-and-test gated. A test named “matches CPU” can allocate a Metal device,
   dispatch a real GPU kernel and compare its result with that oracle. Report
   compiler availability, cfg omissions, ignored tests and actual test counts.
2. **Separate pipeline existence from correctness.** Runtime Metal source
   compilation/pipeline creation can catch missing functions or shader errors.
   It does not prove numerical agreement, route selection or state correctness.
   MSL versions expose different kernels. The current production GEMM requires
   native tensor units; do not infer an older-device fallback from a general
   language-version comment.
3. **Test boundaries against an independent reference.** Preserve BF16 input
   rounding and F32 recurrence/reference semantics. Cover shape/packing route
   predicates on both sides and execute the selected kernels, including tails,
   nonzero views, stacked/sliced layouts and recurrent-state continuation.
   A successful fallback is not evidence that the intended fast route ran.
4. **Use checkpoint-matched goldens for their actual claim.** The selected
   tokenizer and E2E tests are explicitly ignored unless requested; their
   environment variable supplies model files, not proof of the checkpoint
   identity. Tokenizer/template parity and a greedy continuation golden are
   separate checks. Neither alone qualifies the HTTP API, cache isolation or
   concurrency. Send those to [serving-cache](../serving-cache/SKILL.md).
5. **Audit supplied records before interpreting speed.** The bundled
   [record auditor](scripts/audit_benchmark_record.py) checks a saved Lily report's
   selected source/mode/count/finite-value/digest consistency without importing
   MLX, launching a process or reading a model. Its success means only internally
   consistent supplied metadata; it authenticates no execution or binary bytes.
6. **Match the metric and version contract.** Published comparisons measure
   in-process free-running production generation, not identical isolated graphs
   or HTTP E2E. Preserve the distinct prefill-first-yield and decode-inter-yield
   boundaries, exact-shape warmup and drained unused lookahead. MLX computes
   full-vocabulary logprobs that Lily does not expose. Per-engine repeated token
   digests are not cross-engine numerical equivalence.
7. **Keep refusals and negative boundaries.** Source/version mismatch,
   incomplete arms, nonfinite/unstable timings, changed repeated digests,
   interference or power/thermal uncertainty cannot become a valid result by
   selecting the favorable rows. Preserve that the later MLX report has
   long-context prefill cases where Lily is slower, despite its reported decode
   advantage. Never transfer ratios across package versions, models or devices.

## Report and stop

Return executed/failed/ignored/cfg-omitted/not-run checks separately, the exact
artifact identities, workload and metric boundary, counterexamples and remaining
native/model/service gaps. No compiler means Rust checks were not run; no
supported Mac or checkpoint means required native evidence remains
`BLOCKED_REQUIRED_BACKEND`. Python fixture or static-record checks do not clear
that gate and establish no skill efficacy or campaign PASS.

Stop at unsupported hardware/model/layout, unresolved report-version identity,
failed numerical/state/quality gates, missing frozen evidence or the authorized
budget. Reading this skill grants no toolchain installation, model download,
process survey, benchmark run, host change or candidate promotion authority.
