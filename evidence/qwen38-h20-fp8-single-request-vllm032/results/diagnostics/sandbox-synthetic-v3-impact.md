# Pinned EvalPlus executes four trusted cases correctly

Refs [Issue #67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**INCONCLUSIVE for generated-code executor qualification, task quality and E2E.**

CPU2009 completed0:0 in116seconds on4CPUs/zeroGPUs; its allocation is released.
The actual pinned evaluator API processed four handwritten cases inside the
isolated runtime: correct gives pass/pass, plus-only wrong gives pass/fail,
exception gives fail/fail, and per-input timeout gives fail/fail. The timeout
classification follows the pinned evaluator's exception handler, not its outer
process timeout. These deliberately mixed synthetic cases are not a model
accuracy benchmark. The evaluator call took11.31006149307359seconds; outer probe
exit0, no outer timeout, empty outer stderr. Captured evaluator progress and
results remain intact.

The trial uses parallel1, explicit2GiB per-process memory and test_details=True.
It inherits CPU2006's loader policy and authenticates that actual successful
reference. The before/after25,241-entry readonly inventories are byte-identical;
only the probe entry differs from the2006reference. All43 pinned EvalPlus Python
source checks and the same97-package metadata inventory remain present. All nine
postflight checks return0. Actual wrapper/runtime/probe bytes are retained.

The supervisor collected857samples. Observed maxima are5processes,10threads,
412,422,144summed RSS bytes,4,910,592,000summed VMS bytes and58summed descriptors;
these maxima need not occur in the same sample. There was one per-process
observation error, whose reason was not recorded. The failure list is empty,
the observer joined, no known live descendant was observed after exit, and the
inner parent reported zero live children. Polling can miss transient processes:
these observations do not establish aggregate hard limits or exhaustive cleanup.

Independent pre-run review reran18 completion and13 benign-reference controls.
Nine inherited snapshot Ruff findings are disclosed; the newly authored control
and shell syntax checks pass. The prospective plan remains a historical
pre-execution record. Failed and rejected earlier attempts remain retained.

No heldout benchmark task or model-generated program ran. No service benchmark
or measured E2E effect. Full generated-code qualification still needs a bounded
execution policy and cleanup evidence before entering the frozen quality
protocol; this trial does not activate that protocol or performance search.
Readiness GPU consumption remains2388/7200seconds, initial147separate.

KnowledgeStore candidate `case.qwen38-eval-sandbox-preparation-cand` revision `sha256:6d008608b3221cf8d5e9874913ed16a898389c3bf4ae74f2d817eed980caf15d`; readback verified.
