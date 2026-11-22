# MiniCPM Seed-TTS evidence

The service result remains **INCONCLUSIVE**: the retained tuning runs do not
establish lower RTF than the independent engine at C1/C16/C32 with unchanged
speech quality. Acceptance is [#431](https://github.com/InferMatrixLab/InferRSI/issues/431);
implementation is [vLLM-Omni #10331](https://github.com/vllm-project/vllm-omni/pull/10331).

This is a bounded pilot of proposed [RFC #464](https://github.com/InferMatrixLab/InferRSI/issues/464).
Git retains conclusions, numerical summaries, every retained trial's index,
acceptance/configuration/source identities and executable checks. The versioned
external archive preserves **all 56 files / 10,430,698 bytes** from
`dec7a734f27215092f62728f78b98fe26cd58ba2`, byte-for-byte, including the historical
README, raw request records, rejected patches and frozen validator. No experiment
was rerun and no historical verdict or frozen file was rewritten.

## Results and limits

The independent S3 final's median component call latency was **4.2791 → 3.7187 ms
(13.09% lower)** across three alternating measurements per arm. Exact codec tokens
and lengths were checked on synthetic inputs and 16 real references. That local
PASS covers only repeated 600/1200-frame S3 replay, with a two-shape capacity;
it does not qualify the service. The minimal component patch and frozen validator
remain in `patch/s3-component.patch` and `validator/check.py`.

The latest service comparisons each use 64 tuning requests, two repetitions per
concurrency, disjoint warmups and the same reserved GPU. RTF below is the mean of
request RTFs, averaged across the two repetitions; brackets show their min–max.
These are within-server repetitions, not fresh-server uncertainty estimates.

| Mean RTF [repetition range] | C1 | C16 | C32 |
| --- | --- | --- | --- |
| Phase-14 FP32 control | 0.06070 [0.06032–0.06109] | 0.23153 [0.21428–0.24879] | 0.33311 [0.32437–0.34185] |
| Phase-15 Flow FP16 | 0.06069 [0.06029–0.06109] | 0.23159 [0.19614–0.26703] | 0.30565 [0.30310–0.30819] |
| Phase-14 paired engine | 0.06424 [0.06313–0.06535] | 0.21633 [0.21328–0.21937] | 0.26031 [0.25178–0.26884] |

All cells above completed without request failures. Flow FP16 reuses the immediately
preceding control and engine; it has no new paired control server. C16/C32 still
miss the target. WER, embedding-cosine SIM, separately labelled WavLM speaker
verification and UTMOS are descriptive saved-audio scores. Five fresh-server,
held-out comparisons and a resolved speech-quality non-inferiority result remain
missing. FP16 per-replica capture logs, chunk-gap arrays and private traces are
unavailable publicly; aggregate flags do not establish those observations.

Negative and incomplete results remain discoverable in the index and archive:

- The four-worker CPU reference configuration worsened C16 RTF to 0.39736 despite
  speeding up the isolated workload. Its isolated speedup is not a service gain.
- The four-replica run was interrupted; its last C32 cell failed 61/64 requests.
  All six cells of that run are excluded from comparative conclusions.
- Three early screens used a locally modified S3 dependency and were excluded;
  their original raw measurements were never published. Later screens isolate
  the published S3 0.3.0 wheel.
- Pruned configurations, rejected unpadded/onset changes, asynchronous/batched
  history and sampling screens are retained. Matching HiFT precision to the
  running service removed the apparent microbenchmark gain; no service treatment
  was run for that hypothesis. The historical README preserves each interpretation.

## What to inspect

| Record | Purpose |
| --- | --- |
| [summary.json](results/summary.json) | All 144 service groups, counts, failures, repetition mean/min/max/stdev, quality metrics, configurations and both component assessments |
| [trials.jsonl](results/trials.jsonl) | 340 stable trial IDs with archive ID, original file/JSON pointer, execution status, eligibility and conclusion/scope |
| [artifacts.json](results/artifacts.json) | The sole authority for the archive URL, SHA256, bytes, format, source revision, key paths, versions, retention owner and availability limits |
| [core-integrity.json](results/core-integrity.json) | Hashes of retained core files, separate from the frozen archive's original integrity map |
| [pilot.json](results/pilot.json) | Git-blob size comparison, coverage and executed archive verification |
| [service-review-provenance.json](plan/service-review-provenance.json) | Exact source/config chains, dependency and validator identities, launch and workload context |

The index contains 288 service cells, 30 diagnostics, 16 managed component
executions, three pruned proposals and three excluded early screens. Execution
statuses are 333 completed, one interrupted, three not run and three not recorded;
completed means execution completed, not experiment accepted. Of the service cells,
270 retain 17,280 request records; 18 are aggregate-only. Each source/variant/C/repeat
is distinct. Per-request samples and per-utterance diagnostic rows are not trials.
Coverage means all retained public result trials, not unknown private executions.

`plan/` retains the acceptance, RunSpec and exact config chains. Phase-5 source is
reconstructible from the recorded baseline and `patch/service-phase5-source.patch`;
other experimental patches remain at their original paths inside the archive.
The frozen component validator retains its generic `/data/models` mount and needs
the pinned private/local model and dataset assets for a GPU reproduction.

## Verification and retention

From the repository root, using Python with NumPy and PyYAML installed:

```bash
# Explicit network access; no download is added to default CI.
python evidence/minicpm-vllm-seedtts/validator/verify_archive.py --download
# The same verification using a separately downloaded archive:
python evidence/minicpm-vllm-seedtts/validator/verify_archive.py --archive <ARCHIVE_PATH>
# Regenerate summary/index from the verified, extracted frozen bundle:
python evidence/minicpm-vllm-seedtts/validator/build_core.py --snapshot <EXTRACTED_BUNDLE> --output <OUTPUT_DIR>
```

The checker validates metadata, downloads from the pinned Release location, checks
compressed bytes and SHA256 **before extraction**, bounds files/expanded bytes/time,
rejects unsafe paths/links/special files, verifies all original file hashes, then
recomputes the entire index and summary. Structure, IDs and integers compare exactly;
finite floats use absolute tolerance 1e-12. It also runs the preserved CPU validator:
270 service cells, 17,280 timestamp-derived RTFs, 12 configs, nine phase-6 bootstrap
intervals and six speaker-verification records. Errors identify their stage and
return nonzero without changing historical verdicts. This does not rerun GPUs,
validate inaccessible audio/models or qualify the service.

The repository inventory references `artifacts.json` through its existing
`archive-sha256` adapter. Offline checks validate metadata and report the absent
local archive as unavailable; only the explicit download check establishes remote
availability at that time. Proposed shared tooling in PR #328 is not a dependency.
The named retention owner and immutable-version policy live in `artifacts.json`.
Missing original private artifacts remain explicit; hashes alone do not prove access.

The public asset was uploaded and downloaded successfully before removing raw
files from this branch's final tree. The pilot's 512 KiB/file and 2 MiB/net-evidence
thresholds are reporting references only. **Squash merge is required** to avoid
introducing this PR's earlier large blobs into main ancestry; this follow-up commit
alone does not erase them from branch history. No main history rewrite or global
policy/CI change is included.
