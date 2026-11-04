# Proposed paired performance execution protocol

Refs [Issue67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**INCONCLUSIVE / NOT ACTIVATED.** This supplements `freeze-proposal.md`.
Owner confirmation of the statistical/retrieval policy remains necessary.
This document is prospective; it does not relabel the readiness runs.

## Request and timing unit

Use the authenticated official vLLM 0.32.0 streaming request function for both
arms, with the exact pretokenized performance fixture and return-token-ID
extension. Concurrency is one and no requests overlap. Greedy generation uses
ignore_eos and exactly 2048 output tokens, with cross-request prefix caching off.
Authenticate every actual input echo, generated ID count, usage count, terminal
length reason and unique final DONE. Missing/error/partial responses are retained
and prevent a complete comparison. Multiple token IDs in one SSE choice are
valid upstream coalescing; count timing events and output tokens separately.

TTFT and total latency come from the official client's timing boundaries. The
observer derives TPOT as `(latency - TTFT) / (usage_output_tokens - 1)`. It is not
the mean SSE-event ITL. Report complete latency, 2048/latency output tokens/s,
ITL event distributions and coalescing counts separately. Validate all raw
client records and raw SSE before applying the proposed numerical reducer.

## Pairing, order and restarts

A complete comparison keeps one physical allocated GPU for both arms throughout
all three repetitions. Record private device identity and provide a consistent
public device placeholder. Both services never hold the GPU simultaneously.
Repetition order is baseline/candidate, candidate/baseline, baseline/candidate.
Each arm starts a fresh server once per repetition (six starts total), and serves
all thirty fixed cases in order: 8192 s0..s9, 65536 s0..s9, 131072 s0..s9.
Pair observations by exact input ID and repetition, never by nearest timing.

After each server is healthy, warm each length once using its fixed s0 input and
2048 ignore-EOS output tokens. Those three warmups are recorded and excluded.
Then execute the thirty timed requests. Prefix reuse remains disabled during
warmup and measurement. Keep task-owned compilation caches between restarts;
compilation, graph capture and warmup work stay outside timed requests. A failed
warmup stops that arm and leaves the comparison incomplete. No adaptive warmup,
outlier removal, extra repetitions or request retry after seeing timing.

Startup limit is 1200 seconds and request limit is 1800 seconds. The approved
stage/allocation cap always takes precedence. Stop rather than silently shorten
work to fit the cap. A GPU/environment change invalidates pairing; retain the
partial attempt and declare a fresh full comparison prospectively. Final
acceptance reruns the clean delivered candidate with its matched baseline.
The complete paired matrix contains 180 timed and 18 warmup requests: 405504
generated tokens across six service starts, before prefill and startup cost.
Readiness and baseline-only cost measurements cannot be reused as one arm of a
paired final performance comparison.

## Proposed reducer and scope

`validator/proposals/paired_statistics_v1.py` rejects missing, duplicate,
unexpected or invalid records in the 180-request matrix. It reports median of
thirty paired ratios per metric/length, p10/p90, and the proposed input-cluster
bootstrap from `freeze-proposal.md`. A fixed Python `random.Random` seed draws
ten input indices with replacement per draw, preserves all three repetitions,
and reuses the same 10000 draws for every metric/length. The sampled-index digest
is emitted. Linear interpolation defines all reported quantiles.

Only a proposed metric verdict is emitted; campaign verdict stays INCONCLUSIVE
and activated=false. The reducer does not establish source/device/authenticity,
quality, cleanup, approval or validity of a caller's `valid` flag. The final
validator must authenticate those independently before any campaign verdict.
The bootstrap is a per-metric uncertainty rule, not a simultaneous six-metric
confidence claim or a claim about production workloads. Input-cluster resampling
conditions on these same three paired repetitions; it does not estimate
uncertainty from service-restart effects shared across all inputs. Record this
limitation with the owner decision, together with all repetition-level results.

## Remaining activation work

Bind actual service commands/runtime inventories, authenticated sources and all
quality preparation/scoring/sandbox artifacts in an immutable manifest. Resolve
quality readiness, independent review and owner policy confirmation before
search. Baseline-only performance/quality runs require their own declared order,
bounds and complete protocol before execution. No engine performance candidate
is authorized by committing this proposal or by successful synthetic checks.
