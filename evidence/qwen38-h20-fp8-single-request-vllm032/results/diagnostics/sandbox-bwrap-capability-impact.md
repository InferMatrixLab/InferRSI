# Selected bubblewrap lacks four required option names

Refs [Issue #67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**INCONCLUSIVE for isolation/evaluator acceptance; read-only diagnosis completed.**

CPU1999 selected bubblewrap0.4.0. Its captured help text omits --disable-userns,
--assert-userns-disabled, --clearenv and --size; the other four queried options
are present. The selected binary and help are hash-bound. This is consistent
with CPU1998's missing-required-option stop, but1998 did not record the selected
binary identity, so equality across the two allocations is not established.

Slurm records COMPLETED0:0,2CPUs allocated against1requested,zeroGPUs and a
whole-second duration of0; this is not a claim of zero work. The allocation is
released. Only version/help/byte observations and build-tool path discovery ran;
no namespaces were created, isolation behavior tested, packages changed or
Python/evaluator/model executed. Presence in help is not functional validation.
Private tool paths and scheduler details remain outside the public artifact.

A task-local tool providing all required options is the next preparation path;
the exact source/version and build procedure require review before execution.
Do not remove the missing requirements or infer qualification from a newer version.
The already-installed96dependencies plus EvalPlus remain available for a later
inventory/benign retry without repeating installation. No E2E effect or newGPUuse
is measured; readiness stays2388/7200seconds, earlier147separate.

KnowledgeStore candidate `case.qwen38-eval-sandbox-preparation-cand`: `sha256:84fb5a9f6a49e3d1e4b1023c28ae76906ea1c004035a80a17f69a1eba329264c`; readback verified, prior outcomes retained.
