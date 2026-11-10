# Anchoring analytical weight demand against the checkpoint

Status: candidate; `empirical_validation: not_run`. This is a reviewed external
source, read at one pinned commit, recorded in
[`huggingarch-source-identity.json`](huggingarch-source-identity.json). It adds a
**prerequisite check** to the L1 analytical ceiling. It adds no ceiling level, no
bound, and no measurement. Claims below carry one of two markers:

- `[code]` — verified in executable code (statements, constants, signatures) of
  a file inspected at that commit;
- `[doc]` — stated only in the project's own prose: its documentation, or a
  docstring or comment in an inspected source file. Where the behaviour lives in
  a file that was not inspected, the claim is `[doc]` even if a docstring in an
  inspected file describes it.

A parenthesised locator names the file, section or symbol behind the marker.

## Why L1 needs this

L1 divides a work or traffic count by a rated peak. Nothing in the roofline
revisits the model afterwards, so an error in the count propagates into the floor
unchallenged and survives every later consistency check. The failure is quiet:
the formula is right, the division is right, and the number is wrong.

For a checkpointed model the weight half of that count has an external
ground truth — the checkpoint's own tensor headers — that costs one header read
per shard, plus the shard index, and no accelerator. Use it before reporting any
L1 traffic figure derived from a parameter count.

## The anchor is two gates, not one

### Gate 1 — the bidirectional per-tensor join

Join the analytical tensor inventory to the checkpoint header **in both
directions**, on the stored tensor name `[doc]` (`docs/validation.md` §4.1):

- every header tensor must be claimed by an analytical leaf and agree with it in
  physical element count;
- every name the analysis stores must exist in the header.

`CheckpointJoin.of` builds both residuals in one call and carries both as data
`[code]` (`_matching.py`). Several stored tensors may share one name — the same
norm in a dense and an MoE block template, or a multi-token-prediction layer in
the backbone's index space. Their rows are summed before the comparison `[code]`
(`match_checkpoint_to_hf`, `bind_leaves_to_hf`). Summing keeps a correct shared
name from being reported as a spurious layer-count ratio `[doc]` (`HFBinding`
docstring), and a missing copy then appears as a count mismatch `[doc]`
(`docs/validation.md` §4.3).

Both residuals are results, not diagnostics: header tensors nothing claims
(typically a forgotten router gate or expert bias) and stored names selecting
nothing `[doc]` (`docs/validation.md` §4.1, §4.3). Header names are taken
verbatim; the analysis side composes each name from declared root, stack and
module segments, writes a placeholder at each indexed position, and selects
every header tensor that agrees at the literal segments `[doc]`
(`docs/validation.md` §4.2–4.3 and the `_matching.py` docstrings; the lookup and
the name composition live in files not inspected).

Storage bytes are a **checksum on that join, not the primary gate** `[doc]`
(`docs/validation.md` §4.1). The source's stated reason is worth carrying,
because it is the failure a byte total cannot see:

> A sum catches a wrong width but not two submodules swapped with the same
> total, which is why it is secondary.

Compare **bytes, not elements**, wherever precision is mixed: bytes are the only
unit needing no conversion when FP4 routed experts, FP8 attention and BF16 norms
share one file. An element total is reliable only for a single-precision
checkpoint `[doc]` (`docs/validation.md` §4.1).

### Gate 2 — the per-rank weight ledger must build

Gate 1 reads the checkpoint join, **which needs no parallelism layout at all**
`[doc]` (`_weight_ledger.py` module docstring). So an inventory can pass Gate 1
and still be unpriceable per device. The second gate builds the rank's weight
ledger and reports a failure as `weight_ledger_unpriced` (an `UnpricedTensor`)
or `weight_ledger_unbuilt` (any other `ValueError`) `[code]`
(`run_weight_ledger_check`). The documented causes are a tensor with no format
that gives it a width, or a stored weight with no declared layout for a stored
axis `[doc]` (the module docstring and its remedy messages; the errors are raised
in the capacity module, which was not inspected).

The consequence for this skill is the part to remember: **passing a
model-level byte anchor certifies nothing about per-rank weight bytes.** Any L1
figure quoted per device, or under a parallelism degree, needs Gate 2 as well.
A degree that does not divide a weight's part count is handled only as that
axis's declared `fit` policy says — `exact` refuses the deployment,
`replica_cells` lets a group of ranks co-own each shard, `pad` pads each shard
to whole parts — and never by silently rewriting it to a divisor that divides
`[doc]` (`docs/parallelism.md`, stored-weight placement section).

## What the weight anchor does not anchor

The scope statement matters more than the gate, because the gate is persuasive
enough to be over-trusted. In the source's words `[doc]` (`docs/validation.md`
§5):

> The byte anchor sees everything written to disk and nothing about use at
> inference time: how many past positions a query attends to, whether a cache is
> bounded, which nodes are cached. A sliding-window attention and a global
> attention with the same head dimensions have byte-identical weights.

So the anchor covers the **weight traffic term only**. The KV traffic term — the
term that can dominate decode at long context or large batch, and the one whose
growth law decides whether a long context is affordable — is entirely unanchored
by it. A windowed layer wired as dense caches the whole sequence and nothing in
the parameter count reveals it. The source gates that blind spot separately,
through cache-growth laws judged by substituting `s_kv → ∞` into the
stored-length expression `[doc]` (`docs/validation.md` §5.1). Its ablation
module declares a `swa_window` sub-lever implied by `axiom` `[code]`
(`_ablation.py`, `_IMPLIES`). The module docstring and `docs/validation.md` §5.3
tie that lever to the sliding-window capped-cache contract, which the docstring
calls "the 128TB bug" `[doc]`; the gating itself happens in `validate()`, which
was not inspected.

Treat KV counts as carrying their own, separate justification. Do not let a
clean weight anchor imply a clean traffic model.

## Which bound may reject a measurement: the two-threshold rule

This source applies **two different thresholds to the same measured row**, and
grants rejection authority to only one of them. Both are roofline floors, which
[bounds, predictions and decisions](papers-20261015/knowledge/bounds-predictions-and-decisions.md)
treats as conditional physical bounds: conditional on the counts and peak
definitions they are built from. The measured rows they judge make up an
attainable envelope in that note's sense. Only the refusing gate's comparison is
in inspected code.

| Threshold | Compared against | Authority |
|---|---|---|
| Achieved compute or bandwidth exceeds the card's rated peak | the row's own claimed work and **the peak the row itself recorded at test time** `[code]` (`utilization`, `above_sol`) | Row **refused at upload** (HTTP 422) `[doc]` (`docs/measured_calibration.md` §4.3) |
| Measured time faster than the roofline at test time | the estimate's roofline, beside which the measured time is kept `[doc]` (`docs/measured_calibration.md` §7.4) | Row **kept and reported**, carrying an anomaly badge `[doc]` (§7.4) |

The gate function and its comparison are read from code; the refusal is not.
The upload path that returns the 422 is outside the inspected files, so the
refusal rests on the documentation.

The ceiling constant is exactly `1.0` — the rated peak, with no tolerance
margin — and a row that records no peak passes, because the gate judges only
what the row itself states `[code]` (`UTILIZATION_CEILING`, `utilization`,
`above_sol` in `kernel_bench/emit.py`). The comment beside the constant gives
the rationale:

> A row may name the card's own peak, never beat it: a larger claimed rate is
> the signature of a numerator that does not describe the timed launch.

Both thresholds use the engine's own counts. A row's `achieved_*` values are
plan numerators divided by the measured latency `[code]`
(`achieved_from_latency`), and the plan numerators are the engine's per-rank
flops and access bytes `[doc]` (`kernel_bench/emit.py` module docstring). The
gate's docstring frames the refused case as `t_measured < t_sol` on the row's
own numerators and recorded peaks, and the comment above treats such a row as
carrying a numerator that does not describe the timed launch `[doc]` (`above_sol`
docstring, `UTILIZATION_CEILING` comment). Refusal happens at upload. Rows
already stored are restamped when the plan's numerators or the GPU table's peaks
are corrected: their roofline columns are rewritten, never their latency, and
they must pass the gate again `[doc]` (`docs/measured_calibration.md` §4.3).

The source does not say why only the first threshold may refuse. What follows
is this reference's reading, not the source's statement. The upload gate needs
nothing but the row: a row that fails it contradicts itself, claiming more work
per second than the peak it records. The anomaly badge compares the row with a
roofline the estimate computes separately — presumably at query time and from
the estimate's own counts for the op it prices — so a disagreement can mean
either the row or the roofline is wrong. The transferable rule: **reserve
rejection authority for a result that contradicts its own record.** A
rated-peak capacity bound, checked against a result's own stated work and the
peaks recorded with it, may reject that result; correct the record and check
again. A floor computed separately may only flag a result that beats it;
re-derive both sides, do not reject.

## A theory result that no measurement can move

The source keeps a theory result's cache identity independent of measurement
state whenever the result reads no measurements: the measurement scope
contributes to a result's key only when the identity's `reads` flag is set
`[code]` (`ResultIdentity.key` in
`backend/measure/scope.py`). The flag comes from the request
(`reads_measurements()`, not inspected), and call sites beyond `scope.py` were
not traced. The documentation states the consequence: uploads, promotions and
rule changes cannot move a theory key `[doc]` (`docs/measured_calibration.md`
§7.5). A measured time is kept **beside** the roofline rather than replacing it,
and a request may ask for the analytical track alone `[doc]` (§7.4 of the same
document).

This is a useful implementation pattern for any frozen analytical reference:
given a correctly set `reads` flag, the property comes from how the key is built,
not from discipline about when to recompute.

## Archived guard-ablation study

The source reports a study on whether each of its validation gates is necessary.
Carry it with its own header intact `[doc]` (`docs/validation.md` §7):

> This section summarises an archived measurement. It was taken against an
> earlier validator revision, and its harness is not in the repository; the
> results are evidence for the design, not a verified property of the current
> gate set.

Reported result `[doc]` (`docs/validation.md` §7.2): for three models, specs
generated by an agent were 0 % valid with all gates disabled and 100 % valid
with all gates enabled. For one 1 T-parameter MoE model the mean violation count
fell from 32.7 storage (plus 7.3 naming, 4.3 shape, 1.3 KV) to 0, and a 1.8 GB
storage discrepancy to 0. Intermediate tiers were **not monotone** for that
model; only the endpoints were.

Two details decide whether this is evidence or decoration:

1. **The agent's own feedback channel was blinded too.** Disabling a gate drops
   its findings from both the blocking error list and the per-gate warning
   fields — "the two channels a guard acts on" `[doc]` (`_ablation.py` module
   docstring; the dropping happens inside `validate()`, which was not
   inspected). The lever vocabulary and its parent-to-sub-lever expansion are
   `[code]` (`_KNOWN`, `_IMPLIES`, `parse_disabled`). Without the second
   channel, an ablation measures only the publish gate, not the agent's
   self-assessment.
2. **In the unguarded cells the agent exited reporting success**, with its own
   (ablated) validation passing, while the full validator found the spec broken
   `[doc]` (`docs/validation.md` §7.2).

The source's own stated limitations (`docs/validation.md` §7.3): the fault
injector targets cache attributes and a diagnostic kind that no longer exist, so
its unique-coverage matrix is not reproducible without migration; three seeds
per cell give rates rather than single draws, with a run-to-run coefficient of
variation in compute of about 12–16 %; the comparison against the committed spec
is a numeric and structural signature, not op-graph isomorphism; sandbox
isolation relied on de-contamination and a post-hoc scan rather than OS-level
isolation; and three models are not proof of completeness for every model or
fault `[doc]`.

Read against this repository's own rule that agent narrative is never a verdict,
this is consistent, archived evidence from the source project about the cost of
removing its gates; its harness is absent, so it cannot be reproduced here. It
is not a local result and establishes no local gate.

## Facts this reference does not establish

- **No end-to-end validation of predicted against measured serving performance.**
  The inspected documents describe internal consistency (checkpoint anchoring,
  algebraic invariants, dual-path cross-checks) and contain no comparison of a
  predicted deployment figure to a measured one. The source's own residual-risk
  section states that its per-operation axioms cannot verify themselves without
  measurement `[doc]` (`docs/validation.md` §14).
- **Collective communication is not measured** in the source `[doc]`
  (`docs/known_limitations.md` §4.8 heading; the section body was not
  inspected).
- **Corpus scale is unverified.** The companion blog post cites figures for the
  measured corpus that the inspected repository documents do not state. What the
  documents do state is a registry of 361 providers over 124 signatures `[doc]`
  (`docs/measured_calibration.md` §3.5); the six-figure numbers in the same
  documents are service request and memory limits, not corpus size (§4.3,
  §7.2). The tree listing at the pinned commit shows 16 per-library environment
  files directly under `kernel_bench/envs/`; that is a listing fact, not a code or
  documentation claim, and it says nothing about how many rows were measured.
  Do not cite a corpus size.
- **The blog's quantitative examples are not attributable to this commit.** The
  repository was created roughly four weeks after the post and carries a single
  commit with no earlier history, so no inspected revision corresponds to the
  state the post describes. One example from the post's section 2.6, which was
  retrieved verbatim, is recorded here as blog-sourced and unverified: an
  agent-written deployment analysis whose long-context prefill baseline missed a
  factor of 2, which halved a headline speedup until the tool caught it. It is
  kept because it illustrates the tolerance and provenance discipline this
  repository already requires.
- **No local qualification of any kind.** No accelerator was used; no InferRSI
  campaign consumed this source.

## Terminology hazard

The source uses `Class A` through `Class E` for a **verification-rule**
taxonomy: per-operation cost axioms, conservation identities, perturbation
invariants, type contracts and dual-path cross-checks `[doc]`
(`docs/validation.md` §8–13). That axis is unrelated to any bound-versus-estimate
distinction. When citing this source alongside a discussion that also uses
`Class A` / `Class B` labels, name the taxonomy explicitly or use this
repository's four evidence labels instead.

## Readset and verification status

Digests, blob identities and per-file inspection scope are in
[`huggingarch-source-identity.json`](huggingarch-source-identity.json).
`locally_verified` remains `false`. Most files were read in part, and each
file's record states which sections or symbols; a file hash does not imply the
whole file was read. The companion blog post was read in part and is recorded
with that limit.
