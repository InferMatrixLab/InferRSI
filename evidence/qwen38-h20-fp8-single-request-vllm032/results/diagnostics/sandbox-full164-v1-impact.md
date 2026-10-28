# Complete reference evaluation exposes one Plus self-check failure

Refs [Issue #67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**The all-reference-pass control failed; campaign remains INCONCLUSIVE.**

CPU2024 executed the full authenticated164-task canonical reference set and
finished FAILED2:0 in228seconds on4CPUs and zeroGPUs. The allocation is released.
All164 base tasks passed.163 Plus tasks passed; HumanEval/32 returned pass/fail
with seven failed Plus inputs. The expected all164 base/Plus pass condition was
the sole false check. The job's original failure is retained without rescoring,
dropping a task or changing any expected answer, tolerance or official evaluator.
No model-generated program or candidate optimization was executed.

The external-export execution completed and produced the exact133,005-byte
upstream result, SHA256
`3bf8b13d46c1d86838f539e3bf647e61270f40bac4404cd5642e6218c629eb35`.
Inputs, dataset MD5, complete task IDs, canonical solution bytes and result digest
match the execution record and final supervisor hash. Result status metadata was
inspected without exposing problem, solution or failed-input content. The retained
stderr contains no traceback or listed error/warning class; absence of a traceback
does not explain the seven scorer failures, which the upstream evaluator catches.

The pinned evaluator has a special polynomial-residual oracle for find_zero;
its reference-generated expected value does not itself prove this oracle will
pass. This is a source observation, not a demonstrated cause of the seven
failures. Further bounded classification must preserve the official scorer,
source data and original failed result. Final generated-code qualification is
still withheld; this pilot does not establish a trusted all-pass quality oracle.

Official groundtruth construction took16.893428092007525seconds. The full inner
evaluator took42.97722281899769seconds. Cache files totaled254,640,043bytes,
result133,005bytes and final work allocation254,775,296bytes. These are resource
measurements for canonical references, not model performance or peak work usage.
The measured cache plus conservative410,149,174-byte all-failure result bound
fits the1GiB work capacity with the declared1MiB filesystem slack. Actual AS,
CPU, file, task and descriptor limits and work capacity match the new policy.
The16GiB scheduler memory request is not an enforced aggregate hard cap.

All12 other exercise checks pass, including complete result binding, resource
capacity, unchanged runtime, existing-output rejection and four negative controls.
Wrong policy/export and preexisting cache fail with their precise causes and no
score. The one-second supervisor deadline yields no acceptable score and confirms
cleanup; it does not prove solution execution had begun. All five namespace init
and launcher exits are observed with stable final hashes and no cleanup errors.
All12 postflight checks pass. The25,250-entry runtime inventory,97packages and43
pinned evaluator source checks remain unchanged. Original helpers were reused.

Independent source review rejected an unconditional reference-executed flag that
could misreport failed startup. The repaired completion field binds the actual
execution record; original rejected bytes remain available. Eight host binding
controls, two timing-wrapper controls and completion positive/negative controls
pass. Final Linux results remain attributable to the exact12-source manifest.

The owner's subsequent scope amendment makes formal performance and retrieval
8K-only, keeping2048-output requests and TTFT/TPOT<=1.03. Full task-quality scope
is unchanged. No performance search is activated. **E2E optimization effect: not
measured.** GPU readiness usage remains2388/7200seconds, with initial147separate.
Final evaluator qualification, pending statistical decision and complete freeze
remain required. The run supplies measured capacity/time despite its failed
all-reference-pass control; it does not mint PASS from partial evidence.

KnowledgeStore candidate `case.qwen38-eval-sandbox-preparation-cand` revision `sha256:ac7c54a4fc858f8702251830c07253371aa8444fa462f8380f4f362dc7f78777`, readback verified. No protected promotion.
