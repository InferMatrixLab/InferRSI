# Experiment evidence and archive verification

Implements the inclusion/template/tooling slice of the
[scoped archiving decision](https://github.com/InferMatrixLab/InferRSI/issues/464#issuecomment-6913744401).
The RFC's completion and campaign acceptance remain separate owner decisions.

## Repository contents

Retain implementation, necessary tests, goals, conclusions, limitations, key
metrics, effective configuration, input/validator identities, a complete trial
index and verification entry points. Start from [the bundle template](../evidence/_template/README.md).
Small test fixtures stay only when their consumers and necessity are clear.

Archive per-request results, per-sample scores, profiler output, logs, media,
complete source inventories and generated process reports outside Git. Classify
JSON by its purpose; changing directories, minifying, splitting or committing
compressed archives does not justify retaining large generated artifacts.
Do not retain temporary outputs with no review or reproduction value.

Generate summaries and trial indexes from the original control/evidence records.
Record all attempts, including failed, regressing, interrupted and repeated
trials. Retain sample/failure counts, repetitions, variability, metric definitions
and incomplete validation. Preserve frozen raw bytes and historical conclusions.

## Archive authority and schema

Each campaign's `results/artifacts.json` owns its archive metadata. The inventory
references it via `schema: archive-sha256`, `field: archive`, and the expected
local artifact path. Do not copy URL/hash/bytes/owner into inventory entries.
The offline inventory rejects such duplicate `external_assets` metadata.

New documents use **schema_version 2**, illustrated by
[artifacts.example.json](../evidence/_template/results/artifacts.example.json).
Replace placeholders with measured values, including integer byte/file counts.
The executable format contract is `normalize_manifest` in
[tools/evidence_archives.py](../tools/evidence_archives.py).

| Field | Contract |
| --- | --- |
| `archive.id`, `file` | Stable version identity and basename |
| `archive.url` | Credential-free HTTPS download URL; no query or fragment |
| `archive.sha256`, `bytes` | Lowercase SHA-256 and positive compressed byte count |
| `archive.format` | `tar+gzip`; regular nonsparse files only |
| `archive.source_revision` | Immutable 40–64 hexadecimal source revision |
| `archive.root` | Safe relative member prefix, or empty for the whole archive |
| `archive.files`, `uncompressed_bytes` | File count and sum of file bytes under root |
| `archive.key_files` | Named archive-relative files or directory prefixes ending `/` |
| `archive.retention_owner` | Named owner responsible while references remain |
| `verification.inputs` | Archive-relative SHA-256 identities with at least control, configuration and validator roles |
| `verification.command` | Reviewed replay argv, recorded but never executed by the generic tool |
| `verification.trials`, `summary` | Paths relative to retained/regenerated bundle roots |
| `verification.absolute_tolerance`, `relative_tolerance` | Finite nonnegative float-comparison tolerances; integers/structure exact |

Both frozen v1 pilots remain readable through the same normalization function:
`tar.gz`/`tar+gzip`, `files`/`original_files`,
`uncompressed_bytes`/`original_bytes`, and the two source-revision/key-file
locations normalize into one view. Conflicting aliases fail validation. H3's
`snapshot.json` is outside its original-file root; it is still inspected and
counted against safety limits. V1 replay remains with each frozen campaign
checker; normalization does not rewrite either pilot's bytes or interpretation.

## Publication and explicit verification

1. Generate the complete raw artifact locally. Review privacy before publication.
2. Generate summaries and the index from those raw/control records; test coverage.
3. Package regular files, publish a versioned Release asset, and record measured
   metadata. Controlled originals remain in authorized storage under the
   [privacy rules](privacy-security.md).
4. Download again and verify the published bytes and contents with the explicit
   tool. Run the reviewed replay command and compare outputs.
5. Submit the compact bundle, verification results and availability limits.

From the repository root (replace angle-bracket placeholders):

```bash
# Offline metadata only. Never downloads or certifies content.
python tools/verify_evidence_archive.py evidence/<campaign-id>/results/artifacts.json
python tools/validate_evidence.py

# Explicit network operation, bounded bytes/hash/member verification.
python tools/verify_evidence_archive.py evidence/<campaign-id>/results/artifacts.json --download

# Controlled storage: retrieve through its authorized client, then verify offline.
python tools/verify_evidence_archive.py evidence/<campaign-id>/results/artifacts.json --archive <local-archive>

# Separately run the reviewed, pinned replay command from the manifest, then:
python tools/verify_evidence_archive.py evidence/<campaign-id>/results/artifacts.json \
  --archive <local-archive> --recomputed <new-output-directory>
```

The common tool authenticates compressed bytes before tar parsing, then streams
members without filesystem extraction or archived code execution. It rejects
absolute/traversing paths, duplicate names, links, devices and sparse members.
Defaults cap compressed data at 256 MiB, expanded tar bytes (including metadata)
at 512 MiB, files at 10,000, and each download/verification operation at 120
seconds. Downloads have a 10-second socket timeout and permit only GitHub
Release hosts and their HTTPS asset redirects. These are tool resource limits,
not experiment acceptance gates. Larger archives need an explicitly reviewed
tool configuration. Split campaigns only for meaningful storage reasons.

Failures distinguish metadata, unavailable/restricted access, bad bytes/hash,
unsafe paths/members/redirects, resource limits, missing files, bad contents,
trial mismatch and summary recomputation mismatch. Output always states which
scope was checked. Metadata success or verified archive bytes alone leaves
`recomputation: not_checked`; successful comparison reports `outputs_match`.
The caller must review the replay's derivation and coverage; comparing two
identical files cannot prove they came from independent recomputation.

Offline CI does not download, unpack or run a replay. A broken link records a
verification gap without changing the historical verdict. Do not use expiring
CI links or local paths as the only archive source. New bytes require a new
version; keep the old digest/version retrievable. Redacted public copies have
their own identity and explicit limits, never overwrite frozen originals.

## R6 reporting and exceptions

Existing R6 thresholds remain report-only: 512 KiB per `evidence/` file and
2 MiB net evidence growth per PR. This change adds no blocking size gate.
Reconsideration remains on or after 2026-12-02 under the existing decision.

[PR #328](https://github.com/InferMatrixLab/InferRSI/pull/328) owns the pending byte
reporter. Its legacy input can be generated without maintaining duplicate
metadata (after that checker is integrated):

```bash
python tools/validate_evidence.py --budget-assets > <temporary-budget-view.json>
python tools/check_evidence_budget.py --base <base-ref> --report-only \
  --inventory <temporary-budget-view.json>
```

The generated view is disposable, not committed. #328's Release-only URL
format check does not support controlled-store URLs; use the shared reader and
an authorized local archive for those and report that compatibility gap. The
view does not claim remote availability. Added/deleted/net byte reporting
remains in #328's follow-up scope.

Use [the exception record](../evidence/_template/plan/storage-exception.md) when
a specific oversized artifact must stay in Git. Record purpose, consumers,
externalization obstacle, byte count, maintenance owner and explicit maintainer
agreement. An exception record does not create automatic enforcement.

## Cleanup and acceptance

Before removing redundant generated data, identify its consumers and preserve
an exact, retrievable source with digest/size and a concise summary. Convert
behavioral tests to small synthetic inputs when they do not need a full source
scan. Verify links and affected consumers after removal. This removes the file
from the current tree, not existing Git history.

This workflow does not automatically migrate frozen merged campaign evidence.
An explicitly requested, scoped cleanup may replace the current presentation
only after every original file is preserved in a verified versioned archive;
original frozen bytes, historical conclusions and Git history remain unchanged.
For new/unmerged work, externalize before the required squash merge so large
blobs do not enter main. The two pilot archive/replay checks and their
independent reviews remain campaign-specific acceptance records. Completing
this tool or removing redundant data neither establishes experiment PASS nor
closes the parent RFC.

### Scoped legacy record projections

The [H3 four-device bundle](../evidence/h3-ref2va-910c-4logical-20261101-297/README.md)
and [Qwen3.8 bundle](../evidence/qwen38-h20-fp8-single-request-vllm032/README.md)
use v2 for their explicitly requested cleanup. Their full originals, including
superseded cumulative checkpoints and repeated diagnostic code, remain in the
archives. This is not blanket authorization to migrate other frozen campaigns.

`tools/rebuild_model_evidence.py` regenerates compact views from authenticated
originals. `archive.key_files.snapshot` identifies the original per-file hash map;
`archive.key_files.projection` identifies the declarative source/metric selection.
Both and the replay code are pinned by `verification.inputs`. The replayer uses
the common bounded reader to capture authenticated bytes, checks original frozen
manifests, and requires its local implementation to match the pinned code. It
never executes code from an archive and never overwrites an existing output.

Index coverage is deliberately labelled: every published result JSON document
and named/nested attempt observation, including failures and cancellations.
Identical observations of the same named attempt share one row and retain all
source pointers; changed observations, retries and anonymous records remain
distinct. `configuration.record_sha256` hashes canonical JSON for the source
observation. Entry counts are not independent trial counts. Narrative-only
history and unpublished controller records cannot become fully structured
trial evidence through a storage migration; those limits remain explicit.

Declared sample distributions are recomputed; other frozen reported statistics
and verdicts are labelled as recorded values. Replaying the projection does not
rerun inaccessible quality checks, change gates or complete campaign acceptance.
