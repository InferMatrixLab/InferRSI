# Phase-1 acceptance preparation

Parent: https://github.com/InferMatrixLab/InferRSI/issues/53
Acceptance and numeric gates: https://github.com/InferMatrixLab/InferRSI/issues/54

Status: **INCONCLUSIVE; NOT FROZEN**. No model or engine acceptance has occurred.

The first executable milestone compares Transformers full-prefix and incremental
cached execution on fixed raw-text teacher-forced tokens. It establishes a
reference self-check only. Both sides use the same checkpoint and tokenizer.
The independent nano-vllm-derived engine remains a separate incomplete milestone.
Do not describe this bootstrap as engine support, broad model quality or a speedup.

## Freeze checklist

- [ ] BF16 download finished; all required files present.
- [ ] Manifest anchored to immutable public model revision; actual weight and
      config/tokenizer bytes verified against upstream identities.
- [ ] Exact baseline/candidate source and control/validator revisions recorded in
      the acceptance Issue, including dependency versions and imported paths.
- [ ] Workload and validator hashes recorded; ensure each continuation produces
      enough tokens for its requested steps without altering the frozen workload.
- [ ] Numerical gates, resource budget and supported scope frozen in the Issue.
- [ ] Actual single-GPU SKU, runtime and BF16 capability verified in allocation.

`workload.json` is the proposed bounded smoke cohort: English, Chinese, code,
arithmetic, longer prose and a repeated request to detect state contamination.
It does not exercise chat templates, EOS stopping, stochastic sampling, batching,
preemption, prefix reuse, MTP, vision, long-context limits or task accuracy.
Those requirements must be covered before accepting the independent engine for
its declared feature set. Unsupported paths must fail explicitly.

The intended numerical gates from the Issue are per-case NRMSE <= 0.01 (reference
RMS denominator floor 1e-8), top-1 agreement >= 0.99 and exact reset/replay equality.
They are campaign parameters supplied to the validator, never library defaults.

The initial allocation budget is one GPU, 8 CPU cores, 128 GiB host RAM and
60 minutes; the paired experiment deadline is 45 minutes with two AB/BA
repetitions. Model intake verification may need a separately budgeted CPU job.
No optimization search has started. Do not relax gates after seeing candidates;
a changed protocol requires a new freeze and fresh references.
