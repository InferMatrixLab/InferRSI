---
name: qualification
description: "Qualify Splash DFlash2 inference by checking target/draft compatibility, verified-prefix state commits, precision and Metal/Neural Engine controls, reproducibility and fair end-to-end measurement. Use for acceptance-rate interpretation, numerical comparisons, ANE prefill, benchmark attribution or correctness gates."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
---

# Qualify DFlash2, numerical changes and service measurements

This is source-derived candidate guidance. Metal/ANE kernels, model execution,
quality and service performance have not been qualified by reading this skill.
The [verification contract](references/verification-contract.md) contains the
state invariants, controls and evidence ladder. Use
[troubleshooting](references/troubleshooting.md) for misleading acceptance,
changing seeded output, precision differences or an inactive ANE split.

## Establish the comparison

Record engine revision/build and adjacent shader identity; macOS, chip/GPU cores,
memory and power mode; target/draft revisions and file hashes; model/quantization
layout; KV and recurrent-state precision; actual ANE split; verify-row policy;
prompt/template/tokenizer, sampling and penalty settings; context/output limits,
cache salt/hit state, concurrency and observed workload. Freeze the validator,
quality standard, numerical/latency/resource gates and authorized stop condition
before changing a mechanism. Do not import upstream release thresholds as defaults.

## Procedure

1. **Identify the loaded target and draft.** Every selected Splash model uses a
   DFlash2 draft, not a generic interchangeable small language model. Validate
   architecture, hidden/vocabulary widths, mask embedding/token, captured target
   layer IDs and hidden reduction, supported projection formats and actual
   weight images. Matching a model name or bit width is insufficient. Route
   installation/format and total-memory decisions to
   [runtime-planning](../runtime-planning/SKILL.md).
2. **Separate produced, verified, accepted and retained rows.** A cycle drafts
   an anchor and proposals; the chosen verify-row budget and remaining output
   limit bound what the target checks and may commit. API `draft_n` counts the
   draft proposals actually verified, not every produced proposal. Acceptance
   ratio or `1 + accepted / cycles` is not a speedup, quality score or complete
   measure of output work.
3. **Preserve the committed frontier.** Target auxiliary/recurrent state, KV
   visibility, draft rings/context and logical lengths must advance only by the
   retained prefix. Rejected/unverified rows must not become later history.
   Include partial rejection, stop/output limit, thinking-budget replacement,
   constrained masks, unreadable spilled KV, cancellation, suspension and
   restore/continuation. Token truncation alone does not test state correctness.
   Route cache identity/publication to [serving-cache](../serving-cache/SKILL.md).
4. **Choose the reproducibility contract honestly.** MoE `--verify-rows auto`
   uses online acceptance and wall-cost history; identical greedy or seeded
   requests can differ even on an idle server. `--verify-rows all` fixes this
   row-selection source of variation but does not remove batch, prompt-chunk,
   cached-prefix or precision effects. Distribution-preserving acceptance is
   distinct from bit-identical arithmetic or equal RNG consumption.
5. **Control the numerical mechanism.** `--kv-format bf16` changes KV storage,
   not weight precision or GDN state. `--state-format bf16` changes recurrent
   storage and rounds at capture/chunk/decode boundaries despite FP32 compute.
   `--disable-ane` keeps eligible dense FFN prefill on the GPU; MoE, mixers and
   decode are already GPU work in the inspected design. Confirm actual startup
   selection and memory/context consequences instead of inferring activation
   from a flag. Do not change these controls together and call it a kernel-only
   comparison.
6. **Qualify first, then time net work.** Distinguish source/CPU logic checks,
   native Metal/ANE operators, matched-model state/numerical checks and the
   request-level service experiment. Keep startup/calibration/preparation,
   cold prefill, cached TTFT, draft/verify/commit/replay and sustained decode
   separate. Measure admission and completion at the client for E2E latency;
   API timing fields omit the initial admission queue.
7. **Use matched rounds and retain counterexamples.** Compare on the same idle
   machine, power/charger, weights, workload, cache policy and quality contract.
   Keep baseline/candidate/candidate/baseline order and raw samples. The bundled
   [round summarizer](scripts/summarize_rounds.py) reads existing positive
   lower-is-better samples and reports medians/change/spread only; it runs no
   engine and grants no PASS. Apply only the experiment's pre-frozen gates.

## Report and stop

Name the exact observed tuple, quality evidence, actual activated paths, failed
or skipped checks and raw artifact identities. Attribute published benchmark
numbers to their author and original conditions; do not claim local reproduction,
combine ratios across machines or call a native benchmark an agent-task result.

Missing native backend/model evidence remains `BLOCKED_REQUIRED_BACKEND` in
AREX verification and unverified/INCONCLUSIVE for the affected claim. A Python
protocol test or synthetic assertion cannot clear it. Stop at unavailable
resources, a mismatched model/draft/shader, failed state/quality gate or the
authorized budget. Reading this route authorizes neither downloads, client
launches, service exposure, host configuration changes nor candidate promotion.
