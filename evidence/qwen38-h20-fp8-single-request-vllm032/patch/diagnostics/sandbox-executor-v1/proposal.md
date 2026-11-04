# External-export evaluator readiness

Refs [Issue #67](https://github.com/InferMatrixLab/InferRSI/issues/67).
Plane: harness. Campaign verdict: INCONCLUSIVE. E2E effect: not measured.

The prior successful CPU2014 diagnostic wrote its own four inputs inside the
sandbox. This version exercises a parameterized, byte-authenticated external
export: samples, dataset, five-field export manifest and declared cohort identity.
The prototype only permits the exact four handwritten fixture byte streams. A
deterministic comment on the correct fixture makes the raw result exceed the
previous 1 MiB file cap without adding model-generated code or benchmark data.

Pinned EvalPlus uses a default per-process memory guard of 4 GiB. The old diagnostic
overrode it to 2 GiB and imposed a 30-second whole-process CPU limit. Neither is
an unchanged official default or a qualified complete-164-task configuration.
This readiness policy preserves the official memory/timeout defaults with outer
AS 4 GiB, CPU 120 seconds, wall 180 seconds, 64 MiB per-file/output caps, 256 MiB
work tmpfs and 32 MiB shared tmpfs. UID task limit 16, nofile 64, zero core/locked
memory/message queues, readonly runtime/device mounts, network isolation and the
reviewed IPC filter remain. These are finite prototype limits, not accepted
quality gates or a 16 GiB aggregate memory guarantee. Full-dataset resource
qualification remains required.

The actual pidfd capability, startup token and final-output cleanup helpers are
reused unchanged. A fresh child applies the new limits directly; it never first
lowers the old hard limits. Runtime identity covers every executed helper and
policy byte. Per-execution sample/dataset/export/cohort hashes remain separate
from the shared readonly runtime identity. Each run gets a fresh input snapshot,
namespace, work directory, output path and cache. EvalPlus environment settings
are applied before import; its existing-result and ground-truth-cache reload
paths cannot silently reuse a previous invocation's files.

The result validator requires the exact expected cohort, one result per solution,
matching solution bytes, the dataset MD5 used by EvalPlus and known base/plus
statuses. The exact official JSON is retained once after confirmed namespace and
launcher exit. Exit/timeout/cleanup failures yield no accepted score. No protocol
qualification is fabricated: execution records retain `qualified: false`, a
null frozen protocol and an observed runtime identity, so the existing v5 final
score gate remains closed.

One bounded CPU allocation is proposed: 4 CPUs, 16 GiB request, 15 minutes,
zero GPUs, unchanged registered dependencies. Exercise the four official
status pairs, a result larger than 1 MiB, old-output rejection, and actual
wrong-policy/wrong-export failures with empty score output and complete cleanup.
Compare readonly inventories and all source/dependency/binary hashes afterward.
Any incomplete cleanup stops further cases. Keep raw outputs and terminal state
whether the attempt succeeds or fails.

Independent review identified a P2 interface mismatch in preparation: the first
validator and fixture used four export fields, while the actual v5 score.py also
exports `generated_code_executed: false`. The rejected source is retained, and
the revised validator requires that fifth field with the exact boolean type.
Eighteen host-only controls cover this compatibility, input/result tampering,
duplicate/missing IDs, truncation, caps, readonly-command policy and output reuse.
They do not establish Linux behavior or generated-code qualification. Initial
lint findings were corrected before source lock. Formal task quality, full freeze
and same-H20 paired performance comparison remain pending.

Review also rejected a stale-result-digest path: the original driver parsed the final file but retained the earlier supervisor digest without comparing it. The fix hashes the same parsed bytes, requires equality and emits no accepted result digest on failure. Result row task IDs must match their enclosing IDs. Rejected sources remain retained. Negative runtime controls now require the authorization marker and exact digest-mismatch cause, so unrelated startup errors cannot satisfy them. Local bind-failure/timeout controls verify finalization; the initial mock lacked a block-pipe reader and hit BrokenPipeError, and is retained before correction.
