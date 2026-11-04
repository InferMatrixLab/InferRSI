# Anchoring analytical weight demand against the checkpoint

Status: candidate; `empirical_validation: not_run`. This is a reviewed external
source, read at one pinned commit, recorded in
[`huggingarch-source-identity.json`](huggingarch-source-identity.json). It adds a
**prerequisite check** to the L1 analytical ceiling. It adds no ceiling level, no
bound, and no measurement. Claims below are marked `[code]` where they were
verified against the source files at that commit and `[doc]` where only the
project's own documentation states them.

## Why L1 needs this

L1 divides a work or traffic count by a rated peak. Nothing in the roofline
revisits the model afterwards, so an error in the count propagates into the floor
unchallenged and survives every later consistency check. The failure is quiet:
the formula is right, the division is right, and the number is wrong.

For a checkpointed model the weight half of that count has an external
ground truth — the checkpoint's own tensor headers — that costs two or three
HTTP range reads and no accelerator. Use it before reporting any L1 traffic
figure derived from a parameter count.

## The anchor is two gates, not one

### Gate 1 — the bidirectional per-tensor join

Join the analytical tensor inventory to the checkpoint header **in both
directions**, on the full tensor name `[code]`:

- every header tensor must be claimed by exactly one analytical leaf and agree
  with it in physical element count;
- every name the analysis stores must exist in the header.

Both residuals are results, not diagnostics: header tensors nothing claims
(typically a forgotten router gate or expert bias) and stored names selecting
nothing. Header names are taken verbatim; the analysis side composes its names
from declared root, stack and module segments `[code]`.

Storage bytes are a **checksum on that join, not the primary gate** `[doc]`.
The source's stated reason is worth carrying, because it is the failure a byte
total cannot see:

> A sum catches a wrong width but not two submodules swapped with the same
> total, which is why it is secondary.

Compare **bytes, not elements**, wherever precision is mixed: bytes are the only
unit needing no conversion when FP4 routed experts, FP8 attention and BF16 norms
share one file. An element total is reliable only for a single-precision
checkpoint `[doc]`.

### Gate 2 — the per-rank weight ledger must build

Gate 1 reads the checkpoint join, **which needs no parallelism layout at all**
`[code]`. So an inventory can pass Gate 1 and still be unpriceable per device:
every stored weight needs a declared layout for each stored axis and a format
that gives it a width, or no per-rank byte figure exists for it.

The consequence for this skill is the part to remember: **passing a
model-level byte anchor certifies nothing about per-rank weight bytes.** Any L1
figure quoted per device, or under a parallelism degree, needs Gate 2 as well.
A degree that does not divide its dimension must be resolved as declared —
refused, co-owned or padded — and never silently rewritten to a divisor that
divides `[doc]`.

## What the weight anchor does not anchor

The scope statement matters more than the gate, because the gate is persuasive
enough to be over-trusted. In the source's words `[doc]`:

> The byte anchor sees everything written to disk and nothing about use at
> inference time: how many past positions a query attends to, whether a cache is
> bounded, which nodes are cached. A sliding-window attention and a global
> attention with the same head dimensions have byte-identical weights.

So the anchor covers the **weight traffic term only**. The KV traffic term — the
term that dominates decode, and the one whose growth law decides whether a long
context is affordable — is entirely unanchored by it. A windowed layer wired as
dense caches the whole sequence and nothing in the parameter count reveals it.
The source gates that blind spot separately, through cache-growth laws judged
by substituting `s_kv → ∞` into the stored-length expression `[doc]`; its
ablation levers name the gating sliding-window contract after a real
`128TB` cache-size bug `[code]`.

Treat KV counts as carrying their own, separate justification. Do not let a
clean weight anchor imply a clean traffic model.

## Which bound may reject a measurement: the two-threshold rule

This source applies **two different thresholds to the same measured row**, and
grants rejection authority to only one of them. It is an implemented instance of
the distinction in
[bounds, predictions and decisions](papers-20261015/knowledge/bounds-predictions-and-decisions.md)
between a conditional physical bound and an attainable envelope.

| Threshold | Compared against | Authority |
|---|---|---|
| Achieved compute or bandwidth exceeds the card's rated peak | the peak **the row itself recorded at test time** | Row **refused at ingest** (HTTP 422) `[code]` |
| Measured time faster than the op's roofline estimate | an estimate conditional on that op's counts | Row **kept and reported**, carrying an anomaly badge `[doc]` |

The ceiling constant is exactly `1.0` — the rated peak, with no tolerance
margin — and a row that records no peak passes, because the gate judges only
what the row itself states `[code]`. Its stated rationale:

> A row may name the card's own peak, never beat it: a larger claimed rate is
> the signature of a numerator that does not describe the timed launch.

The transferable rule: **rejection authority tracks how invariant the bound is.**
A rated-peak capacity bound, stated per resource and compared against the same
row's own recorded peaks, may reject a result outright — it cannot be beaten
without the numerator being wrong. A per-operation roofline conditional on a
particular set of counts may not, because a different but legitimate
implementation can change those counts. Flag it and re-derive; do not reject.

## A theory result that no measurement can move

The source keeps the analytical track's cache identity structurally independent
of all measurement state: the measurement scope contributes to a result's key
only when that result actually reads measurements `[code]`, so uploads,
promotions and rule changes cannot move a theory key `[doc]`. A measured time is
kept **beside** the roofline rather than replacing it, and a request may ask for
the analytical track alone `[doc]`.

This is a useful implementation pattern for any frozen analytical reference: the
property is obtained from the key's construction, not from discipline about when
to recompute.

## Archived guard-ablation study

The source reports a study on whether each of its validation gates is necessary.
Carry it with its own header intact `[doc]`:

> This section summarises an archived measurement. It was taken against an
> earlier validator revision, and its harness is not in the repository; the
> results are evidence for the design, not a verified property of the current
> gate set.

Reported result: for three models, specs generated by an agent were 0 % valid
with all gates disabled and 100 % valid with all gates enabled. For one 1 T-parameter
MoE model the mean violation count fell from 32.7 storage (plus 7.3 naming, 4.3
shape, 1.3 KV) to 0, and a 1.8 GB storage discrepancy to 0. Intermediate tiers
were **not monotone** for that model; only the endpoints were.

Two details decide whether this is evidence or decoration:

1. **The agent's own feedback channel was blinded too.** Disabling a gate drops
   its findings from both the blocking error list and the per-gate warning
   fields — "the two channels a guard acts on" `[code]`. Without that, an
   ablation measures only the publish gate, not the agent's self-assessment.
2. **In the unguarded cells the agent exited reporting success**, with its own
   (ablated) validation passing, while the full validator found the spec broken
   `[doc]`.

The source's own stated limitations: the fault injector targets attributes that
no longer exist, so its unique-coverage matrix is not reproducible without
migration; three seeds per cell give rates rather than single draws, with run-to-run
compute varying by about 12–16 %; the comparison against the committed spec is a
numeric and structural signature, not op-graph isomorphism; sandbox isolation
relied on de-contamination and a post-hoc scan rather than OS-level isolation;
and three models are not proof of completeness for every model or fault `[doc]`.

Read against this repository's own rule that agent narrative is never a verdict,
this is independent corroboration from a project that measured the cost of
removing its gates. It is not a local result and establishes no local gate.

## Facts this reference does not establish

- **No end-to-end validation of predicted against measured serving performance.**
  The inspected documents describe internal consistency (checkpoint anchoring,
  algebraic invariants, per-operation numerics against a reference) and contain
  no comparison of a predicted deployment figure to a measured one. The source's
  own residual-risk section states that its per-operation axioms cannot verify
  themselves without measurement `[doc]`.
- **Collective communication is not measured** in the source; its interconnect
  term is analytical throughout `[doc]`.
- **Corpus scale is unverified.** The companion blog post cites figures for the
  measured corpus that the inspected repository documents do not state. What the
  documents do state is a registry of 361 providers over 124 signatures `[doc]`;
  the six-figure numbers in the same documents are service request and memory
  limits, not corpus size. The repository carries 16 provider environment files,
  one of which is the reference framework `[code]`. Do not cite a corpus size.
- **The blog's quantitative examples are not attributable to this commit.** The
  repository was created roughly four weeks after the post and carries a single
  squashed commit, so no inspected revision corresponds to the state the post
  describes. One figure the post reports about itself — a 2× error in a
  long-context prefill baseline that halved a headline speedup — is recorded
  here as blog-sourced and unverified, because it illustrates the tolerance and
  provenance discipline this repository already requires.
- **No local qualification of any kind.** No accelerator was used; no InferRSI
  campaign consumed this source.

## Terminology hazard

The source uses `Class A` through `Class E` for a **verification-rule**
taxonomy: per-operation cost axioms, conservation identities, perturbation
invariants, type contracts and dual-path cross-checks `[doc]`. That axis is
unrelated to any bound-versus-estimate distinction. When citing this source
alongside a discussion that also uses `Class A` / `Class B` labels, name the
taxonomy explicitly or use this repository's four evidence labels instead.

## Readset and verification status

Digests, blob identities and per-file inspection scope are in
[`huggingarch-source-identity.json`](huggingarch-source-identity.json).
`locally_verified` remains `false`. The documentation side was read in full for
the files listed; the companion blog post was read in part and is recorded with
that limit.
