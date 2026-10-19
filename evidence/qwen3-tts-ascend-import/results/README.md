# Import verdict: INCONCLUSIVE

**Scope:** InferRSI performance/quality acceptance of the imported techniques.
Reading source and passing catalog tests cannot qualify inference performance.
No NPU inference, audio-quality scoring or matched service A/B was run here.

The source campaign reports a numerical-contract PASS for a combined standalone
engine against two framework baselines. That is an external historical report,
not independent InferRSI validation or an isolated speedup for any imported card.
Raw model weights and generated WAVs are not imported. Public result summaries
and request archives cannot replace independently checked audio/model artifacts.

## Historical evidence navigation

All paths below are relative to the immutable engine source snapshot in
[task #35](https://github.com/InferMatrixLab/InferRSI/issues/35):

| Source artifact | What to inspect |
| --- | --- |
| `compare.md` | Hardware, workload, throughput/TTFA/RTF and quality definitions; commands |
| `evidence/campaign-20261017/plan/final-comparison-runs.json` | Selected baseline/candidate repeats and measured revision |
| `evidence/campaign-20261017/plan/contract.json` | Original campaign contract |
| `evidence/campaign-20261017/plan/quality-gates.json` | Original quality criteria |
| `evidence/campaign-20261017/plan/continuous-direct-prompt-command.json` | Combined candidate flags; not per-feature attribution |
| `evidence/campaign-20261017/results/final-three-arm-performance.json` | Historical throughput, TTFA percentiles and RTF |
| `evidence/campaign-20261017/results/final-numerical-audit.json` | Reported cohort integrity and quality audit, with its stated scope |
| `evidence/campaign-20261017/final-request-records.tar.gz` | Retained request/provenance/scoring records; not pretrained weights or full generated audio |

Use the source's stated frame rate, audio sample rate, warmup policy and timing
boundary. In particular, client semaphore waiting is outside per-request TTFA;
server queueing is inside it. Keep the local-machine and 910B3 cohorts separate.
Historical startup workarounds do not establish an upstream allocator fix.

## Transfer qualification still required

Freeze target source revisions, workload, model hashes, reference outputs and
quality gates in a separate acceptance issue before candidate search. Measure
one mechanism at a time against its direct parent, then the combined stack.
Retain every required concurrency, failed trial and process-exit result. Require
operator checks, complete audio quality and end-to-end serving evidence for a
service claim; verify cancellation, state reuse and graph-output ownership.

## Import checks (CPU, Python 3.12.13)

- `ruff check src tests benchmarks/harness`: passed.
- `python -m pytest`: 222 passed, 70 subtests passed, exit 0.
- Focused catalog/CLI suite: 28 passed, 2 subtests passed.
- Noneditable installed-package check: passed, including all three new records.
- Context export: three records with source attribution and unverified status.
- Source hashes matched fetched public bytes; historical artifact paths exist in
  the pinned source tree. These are source integrity checks, not NPU validation.

The first full run had 221 passes and one failure in the new test because it
omitted the CLI's `--json` flag. The test was corrected before the final run.
Independent review remains pending.
