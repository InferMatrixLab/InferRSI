# Candidate decision cases

All cases are **P** paper-informed review exercises, not reproduced experiments. Status: candidate; empirical_validation: not_run. F evidence links lead to version-pinned readsets and contextual denominators. Expected decisions are proposed rules, not guaranteed outcomes.

## C1. A precise simulator near the wrong boundary

- **Input:** a shortlist claims universal prediction error below9% and selects a candidate just inside its latency SLO at95% estimated capacity.
- **F trigger:** [Vidur V3](../references/vidur.md) reports -12.65% P95 normalized E2E error for LLaMA2-7B/Arxiv-4K at95% capacity, versus different errors at85%; host overhead and queue amplification matter.
- **Expected decision (P):** preserve the candidate as predicted, withhold SLO certification, inspect calibration domain and measure the near-boundary load. Do not mechanically use12.65% as a universal safety factor either.
- **Failure:** promoting a static/kernel error statistic into an online tail-latency guarantee.
- **Completion evidence required:** target-specific request/queue validation under matched resource, workload and metric definitions.

## C2. The fastest probe is not the final deployment

- **Input:** a quick candidate beats the incumbent; subsequent backend/quantization edits break the final server.
- **F trigger:** [InferenceBench I2](../references/inferencebench.md) separates best-seen from final utility, and its structured/warm-start ablations improve preservation without eliminating search gaps.
- **Expected decision (P):** restore the exact last full-valid artifact; restart, warm and verify it through the canonical launcher. Record the fast quick probe as provisional. Reserve time for final verification before further changes.
- **Failure:** calling the task complete from an old metric file or a configuration no longer deployed.
- **Completion evidence required:** same code/config/input/evaluator identity and final valid server, not merely a script that once worked.

## C3. A quality pass hides a false timing boundary

- **Input:** an 8k-prompt server reports near-zero TTFT by streaming a placeholder before model computation; final answer quality passes.
- **F trigger:** [InferenceBench I3 / AppendixF](../references/inferencebench.md) supplies this integrity failure separately from quality failures.
- **Expected decision (P):** reject the timing result and audit the first genuine generated-token boundary, output counts and required model execution. Never recommend the placeholder trick.
- **Failure:** treating score/format compliance as evidence of preserved inference semantics.
- **Completion evidence required:** uncontaminated canonical evaluation plus independent artifact/timing-path validation.

## C4. The next useful optimization is on the CPU

- **Input:** GPU kernels improve but end-to-end throughput barely moves; string materialization and feature assembly dominate.
- **F trigger:** [FlashVector F3–F4](../references/flashvector.md) separates30× serialization-step gain, CPU pod940→about1,500 RPS, and GPU module/forward gains with different denominators.
- **Expected decision (P):** redirect profiling to the exposed host path; inspect immutable-view/buffer-lifetime and semantic lookup eligibility; test a bounded candidate under unchanged CPU/pod budgets. Re-profile after improvement, then revisit batching/concurrency.
- **Failure:** projecting a component multiplier directly into whole-service speedup or treating same-host shared memory as network optimization.
- **Completion evidence required:** correct lifetime/output behavior, component result and end-to-end gain above local uncertainty.

## C5. A selected table row violates its own SLO

- **Input:** a tuning result is labeled compliant, but SLO250ms and measured p99=271ms appear in the same row.
- **F trigger:** [FlashVector Table4](../references/flashvector.md), visually confirmed in the original PDF, contains exactly this ModelB discrepancy.
- **Expected decision (P):** mark compliance unresolved/failing under the stated threshold; seek correction or a matching valid trial before promotion. Do not invent a relaxed SLO or hidden confidence interval.
- **Failure:** trusting a caption or selected-row label instead of checking the actual inequality.
- **Completion evidence required:** corrected provenance or an authorized, measured compliant candidate.

## C6. A huge aggregate speedup comes from a conditional shortcut

- **Input:** a TopK candidate is advertised as universally over1000× faster while many benchmark cases have sequence length≤K.
- **F trigger:** [Agentic Kernel Optimization M7–M8](../references/agentic-kernel.md) bypasses score computation when all valid indices are selected;69/128 cases occupy the all-short regimes. The aggregate is PyTorch-relative; its weighting is unreported. Slow mixed batches have separate underfill and exactness constraints.
- **Expected decision (P):** prove shortcut semantics including ordering/ties/padding; record hit rate and fast/slow/mixed-regime timings; keep vendor-reference comparisons separate. Low DRAM utilization and nonzero achieved occupancy do not by themselves identify spare whole-device throughput.
- **Failure:** exporting a shortcut-dominated average to long sequences, a different output contract, or another device.
- **Completion evidence required:** regime-complete correctness and workload-weighted latency under an explicitly declared aggregation.
