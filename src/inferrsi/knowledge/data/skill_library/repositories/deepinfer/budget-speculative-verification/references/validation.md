# Validation: budget speculative verification

Nothing below has been run. This file records what would establish or refute each claim in `SKILL.md`, so a later authorized test has a target. Numeric thresholds are deliberately absent; they belong to an evaluation plan with a named device, concurrency and workload, because the cost model depends on all three.

## Static and CPU checks

| # | Check | Refutes if |
|---|---|---|
| V1 | Read `EnvVar.bool()` default and confirm the budgeted path is off unless `DEEPINFER_ENABLE_MTP_VARLEN` is set | The budgeted path proves to be default-on, which changes the "off by default" statement |
| V2 | Confirm the draft forward is not throttled by the budget: trace that draft token count is produced before budget allocation | Draft cost scales with the allocation, which invalidates the "verification only" framing |
| V3 | Check exact cumulative values: for conditional per-position rates `p_i`, require `c_i = product(p_j, j <= i)`; preserve inputs already cumulative, including ties and zero rates | Values differ from the required products or already-cumulative inputs are multiplied again; monotonicity alone also accepts an incorrect running minimum |
| V4 | Unit-test the allocator: sorted descending with index tie-break produces a prefix grant for every request, and `best_bsz >= num_seqs` | The allocator can grant a non-prefix set, or the floor can fail |
| V5 | Unit-test the slope clamp with a synthetic negative slope | Extrapolation can produce a non-positive time |
| V6 | Confirm which round's rates the allocator reads for batch size versus per-request length, and that the pairing flag selects between the two stored vectors | The two-round description is wrong, or the pairing flag does not control which vector is used |
| V7 | Confirm the confidence head is presented as a model property, not an engine option | A model without the head could still use the path as written |
| V8 | Confirm the confidence-head temperature is clamped above zero and is applied inside the confidence head | A zero value is reachable, or the value reaches the request's sampling path |
| V9 | Confirm the request sampling temperature is a separate field and is clamped independently | The two temperatures are the same value, which would make F8 wrong |
| V10 | Confirm the reject path is gated on draft logprobs rather than on request temperature | A temperature-0 request bypasses rejection, changing the "greedy still verifies" reading |

## Single-device checks

Correctness and benefit are separate questions and need separate runs. Do not combine them into one before/after token comparison.

### A. Allocation correctness (no sampling semantics needed)

| # | Check | Refutes if |
|---|---|---|
| G1 | Every request receives a contiguous prefix of its draft positions, and at least one row | A request receives position `k` without positions `< k`, or receives no row |
| G2 | The realized row budget equals the value the allocator selected, measured from the built metadata | Metadata disagrees with the allocation, so the budget is not being applied |
| G3 | Hold the historical global budget, the same proposal's legal cumulative prefix through `i`, and other allocation state fixed; perturb only that proposal's later confidence at `j > i` within its signal contract and confirm the verify decision at `i` is unchanged. Check the actual round and queue used; changing historical rates to select a different total budget is outside this test | The same proposal's later confidence changes inclusion of `i` under those fixed conditions; investigate the causal dependency and complete emitted distribution with G5 |

### B. Sampling correctness against an independent oracle

| # | Check | Refutes if |
|---|---|---|
| G4 | Compare the accepted-prefix decision against a separately implemented rejection rule, on synthetic draft and target distributions with known acceptance probabilities | The two disagree beyond the stated tolerance, which means the engine's accept/reject differs from the documented rule |
| G5 | At a fixed prefix compare the complete emitted next-token distribution against the target over many samples, with proposal `q` different from target `p`; include acceptance, rejection/residual resampling and target fallback | The complete emitted distribution differs from the target beyond the predeclared statistical criterion; accepted drafts alone are a selected subset and need not follow the target distribution |
| G6 | Grammar-constrained request under budgeting: confirm the per-position mask and the acceptance rate stay independent signals | One is derived from the other, or masks are applied at the wrong position |

Token-for-token equality between budget-on and budget-off runs is **not** a valid check here. Budgeting changes how many drafts are verified, so it can legitimately change the accepted length and the token stream even with a fixed seed, because the sampling path consumes random draws in a different order. Use G4–G6 instead.

### C. Cost and benefit

| # | Check | Refutes if |
|---|---|---|
| G7 | Report verification rows, accepted tokens and total step time, budget on versus off; assess expected accepted tokens per total time alongside G9 | The declared cost objective or matched service acceptance is not met; rows and accepted tokens falling together is allowed if time falls sufficiently, and their ratio alone establishes no benefit |
| G8 | Report total step time decomposed into draft forward, verify forward and sampler | A component moves in a direction the cost model does not predict |
| G9 | End-to-end throughput and latency at a stated concurrency, with the draft forward included | The gain disappears once draft cost is counted; this confirms the caveat rather than refuting the mechanism |
| G10 | Acceptance-uniformity sweep: all-high, all-low, mixed | Any of the three underperforms plain decode by a margin larger than the allocator's overhead, which bounds where the procedure should be applied |
| G11 | Sampler cost share at production occupancy | Sampler dominates, so the budget cannot help |
| G12 | Peak memory at fixed concurrency, budget on versus off | Memory grows unexpectedly from wide top-k pools |
| G13 | Graph sizes outside the warmup sweep | The fitted slope extrapolates badly outside the collected range |
| G14 | Cross-backend comparison of rejection arithmetic | The two backends disagree, which makes the parity claim false |

## What a PASS would require

Two independent results, not one combined result:

1. **Correctness**: G1–G3 plus G4–G5, at a stated set of sampling configurations.
2. **Benefit**: G7–G9 at a stated concurrency and device, reported as throughput and latency rather than as rows removed.

G1 alone shows only that the allocator does not violate its own invariants. G9 alone shows only that a number moved upward.

## What this skill must not claim

- No efficiency gain. None was reproduced.
- No default behaviour. The budgeted path is opt-in.
- No cross-platform equivalence.
- No transfer to a model without a trained confidence head.
- No claim that accepted length stays constant when budgeting is enabled.
