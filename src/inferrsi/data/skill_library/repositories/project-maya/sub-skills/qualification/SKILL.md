---
name: qualification
description: "Qualify Project Maya speculation, calibration, quantization quality, and benchmark claims without confusing CPU policies or skipped tests with native model evidence."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
---

# Qualification

Use this route for acceptance-versus-speed questions, exactness claims, CPU/GPU
test interpretation, calibration controls, and benchmark or quantization reports.
This is **candidate, backend-unverified guidance**, not a native qualification
certificate. A successful supplied-record audit cannot change that state.

## Route and inputs

- For family, artifact, backend and deployment eligibility, first use
  [model-runtime](../model-runtime/SKILL.md).
- For request IDs, cancellation, prefix reuse, snapshots and cache identity, use
  [serving-state](../serving-state/SKILL.md).
- For the evidence ladder, production callsites, rollback invariants, calibration
  differences and metric definitions, read the
  [verification contract](references/verification-contract.md).
- For skips, noisy tuning, mismatches and incomplete runs, use
  [troubleshooting](references/troubleshooting.md).

Collect the exact family and checkpoint/quantization identity; source and binary
revisions; CUDA or HIP backend, device topology and effective TP groups; context
and KV formats; expert-tier budgets; sampling/penalties; drafting and parallel
settings; workload, warmup, timing boundary, and the proposed claim. Distinguish
explicit settings from startup-selected settings. Do not assume the same name
`Maya-S` identifies the same model across GLM, DeepSeek and MiniMax.

## Procedure

1. **Name the claim before the test.** Host-policy arithmetic, operator parity,
   model distribution quality, greedy token identity and service performance are
   different claims. Freeze the required comparison and falsifier in the owning
   acceptance issue before candidate search; do not invent numerical gates here.
2. **Trace the actual route.** `Controller` simulations do not establish GLM
   `mtp_choose` behavior. Current `DraftPolicy` also has a real DeepSeek lookup
   caller, but its tests still do not run DSpark verification. One-GPU GLM MTP,
   GLM multi-request MTP, DFlash and MiniMax DSpark are distinct routes.
3. **Qualify retained state before timing.** Test a first-draft rejection, a
   middle rejection, full acceptance, stops/forced tokens, context/output limits
   and the next continuation. Count retained rows separately from accepted
   drafts. Check recurrence/convolution state, target caches, NextN cache repair,
   sampler counters and request isolation where applicable.
4. **Preserve evidence levels.** The four selected host slices cover memory
   budgeting, controller simulation, draft-policy simulation and conversation
   victim selection only. GPU kernel tests require real launches; model tests
   require the matched artifact. A missing required backend remains
   `BLOCKED_REQUIRED_BACKEND`, with the performance/model verdict
   `INCONCLUSIVE`, not an ordinary successful skip.
5. **Measure the relevant cost.** Acceptance is not net speed: include drafting,
   verification, commit/cache repair, synchronization and expert-tier work.
   Preserve cold-start, warmup, steady-state, long-prompt and service boundaries.
   A warmed engine decode rate is not HTTP TTFT or concurrent service throughput.
6. **Keep quality independent.** Exact speculative verification against a
   quantized target does not restore the original model's weights or quality.
   Imported reports remain author-reported; qualify each model/quant/backend
   independently, including shallowly mapped community Qwen routes.
7. **Report the actual outcome.** Retain skipped/blocked/failed trials and
   incomplete controls. Name what ran, what did not, and which claim remains
   unsupported. Native kernel parity does not establish L3 quality or L4 gain.

## Offline supplied-record reduction

The original, stdlib-only
[summarize_decode_records.py](scripts/summarize_decode_records.py) reads a small
normalized JSON supplied by the caller, checks its schema and expected source
identifier, and prints descriptive decode statistics. It does not import Maya,
launch processes, contact services, inspect weights or authenticate any bytes.

```bash
python scripts/summarize_decode_records.py --input <RECORDS_JSON> --source-commit <SOURCE_SHA>
```

Run from this sub-skill directory, or use the helper's resolved path. The exact
input contract and limitations are in the
[verification contract](references/verification-contract.md#offline-record-contract).
It reports all execution counts, excludes warmups and non-completed records from
rate arithmetic, and emits no automatic winner, numeric gate or campaign verdict.

## Source boundary

Distilled from `mw00/project-maya` source
`249f9a87d1a9d72bec2b684d704b0aa9296b1c9c` (`VERSION` 1.1.34).
Immutable source locations in the references are provenance, not instructions to
fetch or execute the original checkout. Scope is selected control/calibration,
sampling, test and report evidence; it is not exhaustive kernel or model QA.
