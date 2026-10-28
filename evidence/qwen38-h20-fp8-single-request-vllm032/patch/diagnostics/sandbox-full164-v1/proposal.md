# Complete HumanEval+ reference resource pilot

Refs [Issue #67](https://github.com/InferMatrixLab/InferRSI/issues/67).
Campaign INCONCLUSIVE; no model quality or performance claim.

The next bounded CPU run executes all 164 authenticated canonical references
through the external-export evaluator interface. It permits only exact reference
sample bytes derived from the pinned dataset; it rejects model output. Full task
and solution content remain in controlled storage and are not exposed to the
optimization context. Dataset intake matches the previously prepared final set.
Only aggregate counts, hashes, status counts, timing and resource sizes are shared.

The pinned official EvalPlus revision and dependency installation are unchanged.
The new source keeps official base/Plus tests, test_details=True, parallel=1,
4 GiB default per-process memory and default per-input timeout calculation. It
uses the previously verified startup token, raw pidfd and finalization helpers.
No dependency rebuild or repetition of unrelated isolation modes is needed.

A 4-CPU, 16 GiB request, zero-GPU allocation is limited to one hour. The single
CPU-affinity payload has a 3300-second whole-batch wall bound and 3600-second CPU
limit. Timeout means infrastructure INCONCLUSIVE, never a model-wrong result.
The 16 GiB request is not represented as an enforced aggregate memory cap.

Correction to earlier budgeting interpretation: the ProcessPool coordinator and
worker accumulate their own CPU usage, but each untrusted_check starts a fresh
solution child with reset CPU accounting. Solution CPU does not accumulate in
the reused worker's RLIMIT_CPU counter. Official per-input behavior is unchanged.
The approximate 164 x 2 x 63.2-second worst-case branch waiting sum alone is
20,729.6 seconds, before trusted groundtruth and serialization. This one-hour
canonical pilot does not qualify a worst-case generated-code batch wall budget.

Capacity precheck serializes the exact official result shape with all fixed
base/Plus inputs as failure details and empty solution strings: 7,491,894 bytes.
Six times the separate 64 MiB samples cap bounds ensure_ascii expansion; 4096
bytes add scalar-formatting slack. Total upper bound: 410,149,174 bytes. New
result/FSIZE limits are 512 MiB and work tmpfs is 1 GiB. The actual run measures
reference cache and result bytes, observed rlimits/work capacity, groundtruth and
whole-evaluator wall time. Final work occupancy is not called peak usage. Cache
size plus worst-case output must fit; failure stops qualification progression.

Groundtruth timing wraps the pinned function with unchanged arguments, return
value and exception propagation. The result bytes are emitted unchanged and
bound to the final supervisor hash. Negative controls cover wrong policy/export,
preexisting cache and a deliberate one-second supervisor deadline, with cleanup
and no acceptable score required. Existing-output reuse must fail. Newly observed
resource values must match policy; the program does not fabricate qualification.

Eight host-only input-binding/capacity tests, repository-configured lint and shell
syntax checks pass. The initial source formatting diagnostics were corrected
before the source lock; they were not an execution or optimization result.
Actual Linux outcome remains pending. Success and failure will both be retained
in the evidence tree and revision-bound KnowledgeStore candidate.

Full generated-code qualification/provenance, final finite worst-case budget,
owner-confirmed statistics/retrieval decisions and complete command/validator
freeze remain pending. No performance search is activated. E2E effect: not
measured. GPU readiness accounting remains 2388/7200 seconds, initial147 separate.

Independent review rejected an unconditional reference-executed flag in the
summary, which could misreport a failed startup. The rejected source is retained;
the replacement records only authenticated evaluation completion. A one-second
negative deadline proves supervisor cleanup, not that solution execution began.
