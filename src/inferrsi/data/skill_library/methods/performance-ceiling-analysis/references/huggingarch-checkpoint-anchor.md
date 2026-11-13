# Checkpoint anchor for L1 weight demand

Source: [HuggingArch](https://github.com/shenh10/HuggingArch) at
`facbbbc96856e558b9084a94a5070b2e2c86cf0b` (MIT). The
[source identity record](huggingarch-source-identity.json) gives each file's git
blob, sha256, size and the part that was read.

Status: candidate guidance. `locally_verified: false`,
`empirical_validation: not_run`. HuggingArch was not run, no checkpoint was
joined, and nothing was measured for this document.

## Why L1 needs an anchor

L1 divides a work or traffic count by a rated peak. No later step looks at the
model again, so a wrong count reaches the floor and every comparison made
against it. Typical wrong counts are a projection with the wrong width, a
missing router gate, or a windowed layer wired as global. HuggingArch names this
failure mode and answers it by checking its model description against evidence
the description did not write, the checkpoint first (`[doc]` `docs/validation.md`
§1.1–§1.2). This document keeps the part that anchors weight demand and states
what that part leaves open.

## Markers

- `[code]`: behaviour read in executable code of an inspected file.
- `[doc]`: the source's prose, docstrings, comments or message strings. It also
  covers behaviour implemented in a file that was not inspected, even when an
  inspected docstring describes it.
- `[tree]`: a fact read from the commit's tree listing, such as a file being
  absent.
- `[blog]`: the companion blog post. It is a live page published before the
  pinned commit existed, so nothing in it is attributable to the pin.
- **Reading:** this document's own interpretation, not a source statement.

Every marker carries a locator. Line numbers refer to the files at the pin.

## Gate 1: the bidirectional per-tensor join

### What the source does

- The stored tensors the model description declares are joined with the
  checkpoint header on the tensor name, and the join is read in both directions.
  `CheckpointJoin.of` builds two residuals: header tensors that no stored name
  selects, and stored names that select no header tensor (`[code]`
  `backend/arch/validate/_matching.py` L324–342). The source names them
  `unmatched_hf_tensors` and `checkpoint_name_absent` and gives a forgotten router
  gate or expert bias as the typical unclaimed tensor (`[doc]`
  `docs/validation.md` §4.3).
- A buffer computed at load may be missing from the file, so buffers are skipped
  in the absent direction (`[doc]` `_matching.py` L307–308; `[code]` L336).
- An empty header is refused as unavailable rather than joined. The docstring
  gives the reason: an empty set would pass every stored tensor (`[code]` L327–330;
  `[doc]` L325–326).
- Stored rows that share one name are summed before the comparison
  (`[code]` `match_checkpoint_to_hf`, L157–171). The source's examples are an
  `input_layernorm` stored by both the dense and the MoE block template, and an
  MTP layer that reuses the backbone's index space; a missing copy then shows up
  as a count mismatch (`[doc]` §4.3; `HFBinding` docstring L195–200).
- The per-name comparison counts physical elements: each row's stored bytes over
  its dtype width, times its copy count (`[code]` L169–171). An INT4 weight packed
  into `I32` therefore counts as `I32` elements (`[doc]` docstring L144–147). A
  row whose dtype is unknown stays in the table, marked, instead of being dropped
  (`[code]` L163–168).
- Header names are taken verbatim. A stored name writes `X` at each indexed
  position and selects every header tensor that agrees at the literal segments
  (`[doc]` module docstring L22–26; §4.3). The selection itself is implemented in
  `backend/hf/header.py`, which was not inspected. Each stored name is composed once
  from the declared root, stack and module path (`[doc]` §4.2).
- Which results block publication is decided in
  `backend/arch/validate/_orchestrator.py`, which was not inspected. The gate table lists the unclaimed tensors, a per-name physical
  element mismatch (`param_mismatches`) and the absent names as gates (`[doc]`
  §3, first row). The docstring of `match_checkpoint_to_hf` calls its output a
  per-tensor diagnostic (`[doc]` L16–17, L141–147). The source does not settle this
  within the inspected scope; the procedure below treats a mismatch as a failure.

### Byte totals are a checksum on the join

- Two byte totals follow the join. One compares weights plus declared buffers
  with the header's model storage bytes; the other compares the whole checkpoint,
  scale siblings included, with the byte spans that the shard headers record
  (`[doc]` §3, second row; §4.1). The model storage total leaves out
  quantization sidecars (`[doc]` comment in `_get_safetensors_data`, `_matching.py`
  L79–88).
- Totals are compared in bytes because bytes need no unit conversion in a
  mixed-precision checkpoint, for example FP4 experts, FP8 attention and BF16
  norms in one file. The total element count is reported only as a diagnostic
  (`[doc]` §4.1, §6).
- The source keeps the sum secondary for a stated reason: it catches a wrong
  width, but not two submodules swapped with the same total (`[doc]` §4.1).
- On the estimate path, a per-name element mismatch whose bytes agree within a
  relative 1e-6 is treated as a packing artefact and not reported
  (`[doc]` module docstring L18–20; `[code]` `spec_vs_tensors_check`, L412–424). **Reading:** that tolerance
  belongs to a warning path. It is not part of the gate and is not carried into
  Gate 1.

### Procedure

1. Read every shard's safetensors header: tensor names, dtypes, shapes and data
   offsets. One header read per shard is enough. Loading mechanics stay with
   [weight-loading-optimization](../../weight-loading-optimization/SKILL.md).
2. List every tensor the L1 count includes: weights, biases, quantization scale
   siblings, separately stored tied copies and split parts. Give each a name
   pattern (`X` at indexed positions), stored dtype, stored shape and number of
   stored copies. Mark tensors computed at load as buffers.
3. Join both ways. Record the header tensors no listed name selects, and the
   non-buffer names that select nothing.
4. For each listed name, sum every row that shares it. Compare the sum's physical
   elements with those of the header tensors the name selects. The per-name
   comparison stays in elements.
5. Then compare byte totals: listed weights plus declared buffers against the
   header's non-sidecar bytes, and everything including scale siblings against
   the shard data spans. Only these totals switch to bytes.
6. The gate passes only when both residuals are empty, no name mismatches and
   both totals agree. Equal totals with a residual or a mismatch is a failure. A
   header that cannot be read means the gate could not be judged, which counts as
   a failure.

## Gate 2: the per-rank weight ledger

### What the source does

- A separate check builds the per-rank weight ledger that every view prices
  weights from (`[doc]` docstring L3–9). When it cannot, the check returns one
  finding, `weight_ledger_unpriced` or `weight_ledger_unbuilt` (`[code]`
  `backend/arch/validate/_weight_ledger.py` `run_weight_ledger_check`, L37–51).
- What makes the ledger fail is decided in the capacity and layout code, which
  was not inspected. According to the module docstring and the finding messages,
  a stored weight with no `weight_axes`, or a tensor with no format to give it a
  width, cannot be priced (`[doc]` L1–10, L25–34).
- The source gives the reason for a second gate: the byte anchor reads the
  checkpoint join, which needs no layout, so it cannot see a weight that the
  layout cannot place (`[doc]` L11–14).
- Each weight-bearing node declares, per stored axis, either that the axis is
  replicated, or that it is split on a named parallel world with a `parts`
  expression and a `fit` policy. Nothing is inferred from a symbol being
  shardable; a stored tensor without a declaration is rejected (`[doc]`
  `docs/parallelism.md` L71–93).
- A degree that does not divide a weight's part count is handled only as its
  `fit` says. `exact` refuses the deployment. `replica_cells` lets a group of
  ranks co-own each shard, with the part count split `gcd(parts, degree)` ways
  and replicated across the rest. `pad` pads each shard to whole parts. There is
  no silent largest-even-divisor rewrite (`[doc]` `docs/parallelism.md` L95–102;
  `docs/evaluation_model.md` L172–176).
- A model description declares one placement per weight, although two serving
  frameworks may split the same weight differently. The source documents the
  resulting under-billed weight read and over-billed communication for the
  framework that differs (`[doc]` `docs/known_limitations.md` §1.3).

### Procedure

1. For every stored weight, declare each stored axis as replicated or split on a
   named parallel world, with its part count.
2. Give every stored tensor a format, so that it has a width.
3. When a degree does not divide a part count, apply a declared policy: refuse,
   co-own or pad. Price a padded rank at its padded width. Never substitute a
   divisor that divides.
4. Use the placement of the framework release that will run, and name it.
5. Report per-rank or per-degree weight bytes only after every stored weight has
   a placement and a width. Until then the per-rank figure is
   `INSUFFICIENT_EVIDENCE`.

Gate 1 needs no layout, so passing it says nothing about per-rank bytes. Gate 2
checks the declared layout and format. It does not observe the placement a
framework actually uses at run time.

## What the weight anchor leaves open

- The checkpoint records what is stored, not how it is used. A sliding-window
  and a global attention with the same head dimensions have byte-identical
  weights. A windowed layer wired as global caches the whole sequence, and
  nothing in the parameter count shows it (`[doc]` `docs/validation.md` §5).
- HuggingArch covers that gap with separate gates on the derived cache: reviewed
  KV-growth claims, an active-window presence check and a sliding-window
  contract. §5.1 decides boundedness by substituting `s_kv → ∞` into each stored
  length; §5.2 and §5.3 require growing cached tensors to cap (`[doc]`
  §5.1–§5.3). They are outside this document. Gates 1 and 2 do not anchor KV size
  or growth.
- No gate covers the precision at which a cache slot is stored, because no
  checkpoint byte records it (`[doc]` §5.5).
- Activation traffic, collectives and achieved rates are not anchored by the
  checkpoint.

## Which bound may reject a measurement: the two-threshold rule

HuggingArch compares a measured kernel time with a roofline in two places, with
different consequences.

1. **At upload, a row that contradicts its own record is refused.** `utilization`
   divides the row's achieved compute and bandwidth by the peaks the row recorded
   at test time; a side with no recorded peak scores 0 and is not judged.
   `above_sol` returns a reason when either ratio exceeds
   `UTILIZATION_CEILING = 1.0` (`[code]` `kernel_bench/emit.py` L32, L38–53,
   L284–303). The comment beside the constant gives the reason: a larger claimed
   rate means the numerator does not describe the timed launch (`[doc]` L30–31).
   The upload refuses such a row with HTTP 422, and a row whose roofline columns
   are restamped must pass the same check (`[doc]` `docs/measured_calibration.md`
   §4.3).
2. **At estimate time, a row faster than a separately computed roofline is
   flagged.** When the caller supplies both FLOPs and bytes, the roofline is
   recomputed from those numbers at the row's own test-time peaks, as the larger
   of compute time and memory time. A row whose latency is below
   `ANOMALY_THRESHOLD = 0.95` of that roofline is labelled `measured_anomalous`,
   and its time is still returned, unclamped. If either number or either
   test-time peak is missing, no flag is computed (`[code]`
   `backend/inference/op_calibration.py` L59, L810–819, L924–939).

Separately, when the current GPU table's peaks differ from the row's test-time
peaks, the returned latency is rescaled by the ratio for the resource the row
saturated: compute if its compute utilization is at least its bandwidth
utilization, otherwise memory. A row below 0.5 utilization on both sides takes
the slower of the two rescaled times. If either compute peak is unstated, the
compute ratio is 1 (`[code]` L344–345, L745–807).

**Reading:** rejection is reserved for a row whose own numbers are inconsistent.
It claims more work per second than the peak it recorded, so its numerator or its
peak is wrong. A floor computed from other counts can only flag, because a fast
row may mean that the floor's count or peak is wrong, not the row.

For InferRSI:

- Reject a measured row against L1 only when the row's own work over its own time
  exceeds its own recorded peak. Correct its numerator or its peak, then check it
  again.
- Flag a row that is faster than a separately computed L1 floor, and re-derive
  both sides: the count through Gates 1 and 2, and the peak at the clock the
  device actually ran.
- Any numeric tolerance for the flag belongs to the acceptance issue, not to this
  skill.

## Evidence the source offers for the gates

`docs/validation.md` §7 summarises an archived guard-ablation study (`[doc]`).
The source says it was taken against an earlier validator revision and that its
harness is not in the repository.

- An agent regenerated three model descriptions (DeepSeek-V4-Pro, GLM-5.2 and
  MiMo-V2.5-Pro) from scratch in a de-contaminated sandbox. Guards were added
  back cumulatively, with three seeds per cell. With no guards all three were
  0 % valid; with all guards, 100 %.
- The weight guard removed the storage errors. On DeepSeek-V4-Pro, mean storage
  violations fell from 32.7 to 0 and the storage discrepancy from 1.8 GB to 0.
- In the unguarded cells the agent exited reporting success, and its own
  weakened validation passed, while the full validator found the description
  broken.
- The source lists its own limits: the fault injector targets attributes that
  no longer exist, there were three seeds per cell, run-to-run compute varied by
  about 12–16 %, isolation was de-contamination plus a post-hoc scan rather than
  OS-level, and only three models were tested. Intermediate tiers were not
  monotone for DeepSeek-V4-Pro.

The levers the study used remain in the code. `HA_ABLATE_GUARDS` names the levers
to disable, `weight` implies `packing`, and unknown names are ignored (`[code]`
`backend/arch/validate/_ablation.py` L40, L56–77). Per the module docstring, the
`weight` lever covers the byte totals, the per-tensor matching and the per-rank
ledger, and a disabled lever's findings leave both the publish gate and the
agent's feedback (`[doc]` L3–7, L15–17). The dropping happens in `validate()`,
which was not inspected.

**Reading:** this is archived evidence for the design, not a verified property of
the gates at the pin. It was not reproduced here.

## The companion blog post

The post at <https://shenhan.cc/blog/huggingarch> displays the date 2026-10-08.
The pinned commit is the repository's root commit (`init repo`, authored
2026-11-04, no parents); GitHub reports the repository as created on 2026-11-03.
The post therefore predates the pin by about four weeks, and no revision links
its figures to code. It was retrieved once, on 2026-11-10. Sections 2.5, 2.6,
3.6 and 3.7 were read in full.

- `[blog]` §2.6 describes an agent-written deployment analysis of DeepSeek V3,
  V3.2 and V4-Pro on 8×B200 that HuggingArch's accounting contradicted. The V3
  prefill at 1M context was written as 73.48 µs/token, where a first-principles
  recount gives about 150: a missing ×2. Because V3 was the baseline, V4-Pro's
  prefill speedup over V3 read 4.7× instead of 9.4×. The analysis also assumed
  that short-context single-request prefill was compute-bound, when reading MoE
  expert weights from HBM binds it. The analysis was not inspected, so the example
  is unverified. **Reading:** both are L1 errors that roofline arithmetic carries
  forward without complaint, which is the failure this anchor exists for.
- `[blog]` §2.5 says the validator normalizes both header and model-description
  names with `canonical_module_path()` and joins on that key. The pinned code and
  documents describe verbatim header names and `X`-pattern selection instead
  (`[doc]` `_matching.py` L22–26; `docs/validation.md` §4.3). Follow the pin.
- These figures appear in the post but in no inspected repository file. Do not
  cite them as source facts:
  - in a separate experiment with eight coding agents, the share of wrong
    descriptions the agent itself judged as passing: 94 % with no guards and 6 %
    with all guards (§2.6);
  - the cost of one V4-Pro derivation: 62–87 agent turns, 44–63 minutes and
    USD 14–22 (§2.6);
  - a measured corpus of more than 280,000 rows covering 60 models and 13 operator
    libraries (§3.7).
- `[tree]` The post points to `docs/guard_ablation/report.md` for the full study.
  That file is not in the pinned tree.

## What the source does not establish

- No inspected file compares predicted with measured end-to-end serving results.
  The source verifies self-consistency: conservation, perturbation invariants and
  type contracts. Per-op cost axioms can only be reviewed against modelling
  source; the system cannot verify them itself (`[doc]` `docs/validation.md` §8,
  §9, §14).
- Collectives are never measured, so a deployment containing one has no complete
  measured total (`[doc]` `docs/known_limitations.md` §4.8).
- `[tree]` The measured corpus is not in the repository. The tree's only CSV is
  `backend/inference/gpu_specs.csv`, and it holds no Parquet or DuckDB files.
  Measured rows live in a store owned by a separate service (`[doc]`
  `docs/measured_calibration.md` §1.2). `scripts/seed_shared_corpus.py` exists;
  its input was not inspected. The corpus's availability to InferRSI is not
  established.

## Adoption boundary

- No HuggingArch code, model description or measured data is copied. The two
  gates and the two-threshold rule are restated as procedures; nothing here runs
  HuggingArch.
- The source's numeric constants (`1.0`, `0.95`, `0.5` and `1e-6`) are recorded
  as provenance only. InferRSI keeps numeric gates in acceptance issues.
- The source groups its result checks into classes A–E (`docs/validation.md`
  Part II). That vocabulary is not imported.
