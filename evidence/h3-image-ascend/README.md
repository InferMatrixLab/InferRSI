# H3 Image on four Ascend devices: evidence archive

Campaign [#390](https://github.com/InferMatrixLab/InferRSI/issues/390), engine
[PR #10184](https://github.com/vllm-project/vllm-omni/pull/10184).
**Campaign acceptance remains INCONCLUSIVE; all three latency targets are unmet.**
Final isolated ABBA, full visual acceptance and independent cross-hardware
reference quality are incomplete. CPU checks and archive verification do not
qualify the model or change any historical conclusion.

This unmerged-PR pilot applies the storage approach proposed in
[#464](https://github.com/InferMatrixLab/InferRSI/issues/464). It does not adopt
repository-wide policy or migrate merged evidence. The complete public export
at `2e850be2a2f9e4b38e1eec7741be1f406f69a532` is preserved byte-for-byte in the
[versioned Release asset](https://github.com/InferMatrixLab/InferRSI/releases/tag/evidence-h3-image-ascend-v1):
156 original files, 74,543,002 uncompressed bytes. This tree keeps the frozen
configuration and validators, derived summaries, a complete index of the
published records, and an explicit verification entry point.

## Read the results

- [Structured summary](results/summary.json): source/configuration context,
  workload statistics and recorded quality aggregates, grouped by experiment.
- [Trial index](results/trials.jsonl): each HTTP run/comparison, component
  parameter case, execution attempt and diagnostic has an individual entry.
  Repeated configurations retain distinct IDs; failed and interrupted attempts
  remain indexed. Validation-only records are labelled separately.
- [Archive reference](results/artifacts.json): the **single authority** for
  download URL, SHA-256, bytes, format, retention owner and source revision.
  The repository inventory references it instead of maintaining another copy.
- [Frozen workload](plan/workload.json), [quality gates](plan/quality-exploration.json),
  [environment](plan/environment.json), [provenance](plan/provenance.json) and
  [initial engine delivery](patch/revision.json) remain unchanged. The initial
  revision pointer is historical; later revisions are in the summary's groups.

The latest round 24 uses engine base `bd30cbd3fb621fcca600b2de08fc1249c6c0987c`.
It compares the existing opt-in exact text prompt cache with caching disabled;
reference-image calls bypass that cache. Six PDD steps, canvas, transport and
quality gates remain unchanged. Measurements are HTTP POST start through full
response receipt, concurrency one, one warmup then three timed requests per
workload and arm. These are one launch pair, not final repeated ABBA.

| Round 24 | Control median (s) | Candidate median (s) | Target (s) |
| --- | ---: | ---: | ---: |
| W1, text-to-image 4736×3552 | 11.081 | 10.959 | 7.34 |
| W2, text-to-image 1024×1024 | 2.690 | 2.656 | 1.52 |
| W3, editing 1024×1024 | 4.658 | 4.735 | 2.60 |

All 30 matched images were RGB-exact, but the mixed latency changes did not
establish an overall benefit; the candidate was not adopted. Cold/warm cache
semantics and reference-image bypass are retained in the structured summary.
The precise values, sample counts and ranges are generated from archived
samples, not maintained separately from the experiment records.

Earlier comparisons remain revision-scoped. Whole-model W8A8, SmoothQuant,
communication fusion, early NZ conversions and full-step FIA include rejected
quality screens. Post-load NZ, text/row preparation, final-step FIA and async
QKV include mixed or slower latency despite passing their numerical screens.
Component probes retain each parameter case and do not establish service gains.
The low-rank quantization calibration reused architecture/portrait inputs from
the expanded quality suite; these were **not independent heldout inputs**.
The failed first sparse-attention process and its invalid samples remain
explicitly recorded and excluded as in the original export.

The full historical narrative, source fingerprints, per-request records,
quality reports, raw component samples and round-two image gallery are in the
archive at their original relative paths. The original README contains earlier
"pending" observations; later records supersede them without rewriting history.

## Verify or regenerate

Run from the repository root with Python 3.10 or later; these operations are
CPU-only and use the standard library:

```bash
# Offline inventory: layout and available bytes only; no implicit download.
python tools/validate_evidence.py

# Explicit public download, byte/hash verification, and exact view comparison.
python evidence/h3-image-ascend/validator/archive.py --download

# An independently downloaded asset can be verified without network access.
python evidence/h3-image-ascend/validator/archive.py --archive /path/to/archive.tar.gz

# Regenerate the two derived views from the authenticated snapshot.
python evidence/h3-image-ascend/validator/archive.py --archive /path/to/archive.tar.gz --write
```

The verifier authenticates the compressed archive before reading its members.
It checks every original file against the snapshot and original frozen export
manifest, and compares retained configuration/validator bytes. It never executes
archived code or extracts paths to disk. Links, devices, duplicate/unsafe paths,
excessive expansion and member counts are rejected; download/read operations
have size and time bounds. Missing access, wrong bytes/hash, missing files and
view mismatches return distinct failure reasons and a nonzero exit status.

`summary.json` and `trials.jsonl` are deterministic projections of the archived
records, not another experiment controller. Every ID is the results-relative
JSON filename without `.json`, followed by `#` and a JSON Pointer; an empty
pointer selects the entire record. Resolve it beneath the archive's
`h3-image-ascend/results/` directory. Index coverage is checked by regenerating
all IDs and entries, including repeated cases and failures, then comparing the
complete index. Supporting measurements and quality reports are enumerated in
`summary.json` under `coverage.support_records`.

HTTP medians are recomputed from the original sample arrays and compared exactly
to historical medians. Where per-request records exist, measured samples are
also cross-checked against those records after excluding warmups. Counts and
all generated JSON values must match exactly; no new numerical tolerance or
acceptance gate is introduced. Component timing summaries preserve individual
repetition groups; their min/median/max and counts come from raw samples.
Image pass/fail counts and score extrema are recomputed from **recorded checks**,
not by rerunning PSNR/SSIM on unavailable image pairs.

## Availability and integration limits

Most full-resolution images, activation tensors, original candidate source
snapshots and host/profiler logs were never published. Six representative
round-two full-resolution PNGs are archived; the other 24 images in that screen
remain unavailable. Historical source-manifest hashes identify external
snapshots, not source bytes verified by this archive. These gaps existed before
the migration and remain explicit in `artifacts.json`.

The offline inventory reports the absent external archive as unavailable. That
is distinct from manifest validity and from a successful explicit download
verification at a particular time. Loss of future access must be recorded as an
availability gap, preserving the original experiment conclusions. The named
retention owner is `amy-why-3459`; updates require a new archive version.

The repository's existing squash-merge convention is required to keep the
externalized blobs out of the commit entering `main`. The release tag is anchored
to an existing main commit; the evidence source revision is recorded in the
manifest. Old PR commits remain historical references. This change neither
rewrites `main` nor claims to erase previously uploaded Git objects.
