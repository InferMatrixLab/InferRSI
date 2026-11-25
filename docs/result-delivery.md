# Result delivery

Export retained records into a **new** directory:

```bash
inferrsi export --input <campaign-directory> --output <new-delivery-directory>
```

Start with `report.md`. `report.html` is labelled **Open in a browser** and works
offline, including its search curve, tables and expandable structured snapshot.
`campaign-result.json` is the machine-readable result; `artifacts.json` indexes
the reports and source evidence. All four files describe one snapshot.
Code and evidence use digest-bound references to the original input directory;
they are **not copied** into this reference-based bundle. Offline reading does
not imply offline reproduction. Review records and paths before sharing; this
is not an automatic redaction tool.

`campaign final` and `benchmarks session final` call the same Apps exporter after
Harness returns, including a failed final assessment. Output goes to
`<campaign>/delivery/<export-id>/`. The existing execution result and exit code
remain unchanged; `delivery` separately reports publication success, failure or
uncertain durability. A report failure cannot undo a committed final. Retry
export, not measurement. Direct Harness calls remain execution-only. Python
callers can use `inferrsi.apps.delivery.export_bundle` and `read_bundle`.

The export command exits 0 for successful publication, including FAIL and
incomplete reports, and 2 on export failure. It supports progress, blocked tasks
and retained records after termination. A busy writer returns an explicit retry
error. It never starts a missing final, executes a validator, recovers an attempt,
fetches a reference, or changes selection/control state.

## Design decisions and authority

This is the implementation contract for [RFC #468](https://github.com/InferMatrixLab/InferRSI/issues/468).
The RFC remains proposed until its decision owner records adoption. These
resolutions implement the discussion's constraints; implementation and RFC
acceptance remain separate.

1. **Archive authority:** campaign `results/artifacts.json` owns external archive
   metadata under [#464](https://github.com/InferMatrixLab/InferRSI/issues/464).
   Delivery's separate bundle index points to that exact document and digest
   through `archive_authority_ref`. It does not copy archive IDs, URLs, sizes,
   hashes, owners, access rules, availability or integrity. Existing shared archive
   readers own normalization and verification. Delivery's `verified` on this
   entry means the **manifest bytes** were read, not that remote bytes verified.
   No duplicate archive metadata needs reconciliation.
2. **Candidate binding:** selected and final retained code normally verify against
   the same file/directory fingerprint. A no-fingerprint adapter can instead verify
   an exact revision and fixed run/configuration documents, as specified below.
   Missing, contradictory or unverifiable binding preserves the original verdict
   as an audit fact and sets `delivery_accepted: false`.
3. **Degraded reads:** a separate read-only adapter never weakens Harness `_load`
   or reassesses evidence. An intact digest-bound observation retains historical
   PASS when measurement bytes are missing or modified. If the observation is
   missing, invalid or conflicts with committed state, a readable cached assessment
   in `state.json` retains the historical verdict and completion facts, explicitly
   labelled **cached state; unverified**. It cannot establish current delivery
   acceptance. If neither source supplies a readable assessment, the report says
   “Not assessed”; it never invents a verdict or substitutes a search PASS for final.
4. **Snapshot:** native exports share the controller's nonblocking OS lock. Since
   writers hold it throughout an attempt, progress exports happen between committed
   operations. A second digest pass checks every source read, negative lookup and
   candidate member set. Uncoordinated writes trigger at most three complete retries,
   then an explicit error. Native exports never consult `summary.json`. Live elapsed
   time uses one observation cutoff throughout retries.

## Version 1 result fields

Identity: `schema_id: inferrsi.campaign-delivery`, `schema_version: 1`.
All fields below are required. `null` means unknown/unavailable, explained in
`gaps`; an empty collection means known empty. Numbers must be finite. Timestamps
are timezone-qualified ISO 8601. `read_bundle` rejects unsupported versions and
checks entry-file hashes. Optional additions retain the version; changes to
existing field types or semantics require a version increment.

| Field | Meaning |
| --- | --- |
| `export` | ID, generation time, observation cutoff, `progress`/`final`, generator version |
| `campaign` | ID, recorded goal, task kind, frozen acceptance basis, plan reference |
| `sources` | Artifact IDs, source types and exact record digests |
| `execution` | Original state/namespace, budget, settled round count, round policy, stop reason, times |
| `completion` | `completed`/`incomplete` workflow and reason |
| `outcome` | `improved`, `baseline_retained`, `no_valid_candidate` or `undetermined`; selection rationale |
| `baseline` | Retained and observed fingerprints, configuration, source references |
| `selected_candidate` | Controller selection and retained code/configuration, or null |
| `final` | Independent final attempt, protocol, execution, assessment, binding; null if absent |
| `acceptance` | Original status/verdict, claim ID, scope, assessment reference; separate current delivery acceptance |
| `metrics` | Phase/scope/workload comparisons, units, statistic, configuration, sample counts, provenance |
| `checks` | Original assessment/check, requirement, execution, frozen gate, observation, verdict, evidence |
| `rounds` | Ordered attempts, including rejected and unresolved pending attempts |
| `usage` | Wall time, observed tokens, device time and cost, each with source and coverage |
| `gaps` | Missing steps, mapping limits, identity gaps and present evidence failures |
| `artifacts_ref` | `artifacts.json`, without a digest to avoid a hash cycle |

`completed_rounds` counts settled search records, including rejected candidates,
as the controller does. Pending attempts retain their own IDs and do not increment
that count. Retries or independent finals are never invented from summary curves.

Completion requires the frozen round policy (including a permitted early stop's
recorded reason) and a normally finished independent final assessment. A completed
assessment that violates a quality/performance gate can yield completed + FAIL.
A missing/interrupted final stays incomplete. A final snapshot means the source
stopped, not that it succeeded. Historical completion survives later evidence loss;
prominent current gaps prevent current delivery acceptance.

The primary assessment is the final record, never a favorable search result.
For native records, `assessment_provenance` on acceptance, final, checks and rounds
identifies `kind: retained_observation / cached_state`, an indexed `artifact_ref`,
the assessment's `json_pointer` inside that document, and
`verification: verified / unverified`. A retained observation must agree with the
committed record and its recorded digest. A readable cached assessment is used
only when that original cannot be read consistently; its reference resolves to
`state.json`, with `/final/assessment` or `/rounds/<index>/assessment`. Conflicting
values retain an explicit gap instead of choosing the more favorable verdict.
The index still records the missing or damaged observation and raw evidence.
Observation verification does not certify all evidence: `delivery_accepted`
separately requires current evidence and candidate binding to verify. Cached
assessments always remain unverified, even if the other evidence is intact.
Their raw measurements remain in the historical check for audit, but do not
produce comparison metrics, derived gains or usage totals. Cached search scores
remain labelled in the history and curve. Malformed or absent cached assessments
cannot establish historical completion; cached timeouts stay incomplete.

Missing claim identities stay null with `identity_incomplete`. Existing INCONCLUSIVE
is preserved; missing assessments are “Not assessed,” never fabricated INCONCLUSIVE.
`improved` also requires a non-baseline selection, passing verified final and a gain
under the frozen selection direction. Baseline retention and its final verdict are
separate. Baseline optimization speedup is 1.0 only after verified completed final;
its measured A/A ratio remains separate in `metrics`. A blocked state alone cannot
establish `no_valid_candidate`; unsupported selection outcomes stay `undetermined`.

Project measurements use their retained paired median; task `case_metrics` preserve
separate measured cases. Missing workload IDs remain null. No concurrency tiers or
workloads are aggregated, and export establishes no statistical significance.
Positive comparable pairs yield baseline/candidate for minimize and candidate/baseline
for maximize, plus the corresponding improvement percentage. Missing units/statistics,
nonpositive values, inapplicable ratios, overflow and incomparable external records
retain raw values and null gains. Failed search scores leave holes in the HTML curve.

Usage preserves the observed search subtotal separately from the caller session
export, never adds them together, and counts cached input as a subset of input.
Subtotal coverage concerns settled search rounds, not the whole campaign. A final
caller export alone cannot prove complete session coverage. Device time and cost
remain null without accounting observations; elapsed wall time is insufficient.

## Adapter mapping

| Input | Authoritative facts | Deliberate gaps |
| --- | --- | --- |
| Native project / Benchmark | Plan, campaign, state, digest-bound observations/execution/evidence and retained code; labelled cached history if observations are lost | Cached history cannot verify delivery; summaries cannot substitute for final |
| Historical version 1 `summary.json` | Recorded final assessment and reported completion | No reconstructed rounds, independent final, binding or usage coverage |
| Legacy run directory | `run.lock.json`, `status.json`, `evaluation.json`; paired single-experiment median | No invented iterative rounds/final or generalized L4 claim |
| Apps `result.json` | Validated AppsResultV1, explicitly selected primary claim, fixed refs, all original claims | Operation success is not campaign completion; storage is not implicitly mounted/fetched |
| Explicit external record JSON | Version 1 `external_optimization_record`, source refs, performance/quality observations | No local revalidation or inferred comparability |

External JSON uses `--input <record.json>` with references relative to its parent.
Arbitrary files named `result.json` or `summary.json` are not guessed into these
contracts. Campaign-specific historical formats need explicit adapters; unsupported
schemas fail instead of manufacturing facts.

The no-fingerprint extension uses identical `best.binding` and
`final.candidate_binding` objects in retained native records:

```json
{
  "revision": "<full-exact-revision>",
  "run_ref": {"path": "<relative-run.json>", "sha256": "<sha256>"},
  "configuration_ref": {"path": "<relative-config.json>", "sha256": "<sha256>"}
}
```

Revision is a full 40- or 64-character lowercase hexadecimal identity. Both fixed
documents must verify and record that `candidate_revision`. The run also records
the identical `configuration_ref`, final `attempt_id` and frozen `protocol_digest`.
Matching names alone are insufficient. This alternative cannot override contradictory
file fingerprints. It does not implement service-reuse execution in Harness, fetch
Git revisions, or claim local code-byte verification for a revision binding.

## Artifact index and publication

The index identity is `inferrsi.delivery-artifacts`, version 1, with `export_id`.
Entries include ID, role, location/kind (`bundle` or `source`), media type, size,
SHA-256, source revision, availability, integrity, check time and access explanation.
Source locations are relative to the original input unless an optional logical
`source_root` identifies an explicitly supplied additional input. For Benchmark
`--agent-job`, `agent-job` identifies that native job directory and `agent-input-N`
identifies the parent directory of its Nth declared frozen input (zero-based).
These are logical IDs, not filesystem paths; callers bind them to their retained
inputs outside the shared index. Their locators stay relative, and the index never
copies the local absolute roots. Bundle locations are relative to this export.
Known digests survive missing/corrupt bytes; `observed_sha256`
separately records the current bytes. The index hashes JSON and both reports, not
itself. Both reports display the JSON digest and export ID.

Reports escape imported text and use only fixed local navigation links. There is
no executable embedded data or arbitrary URL fetching. V1 does not bundle arbitrary
attachments, follow symlinks or traverse outside each declared input root.
Documents have an 8 MiB read limit. Oversized optional documents are indexed as `unreadable` with
integrity `not_checked`, retaining the expected digest without reading or hashing
their bytes, including during snapshot rechecks. They allow labelled cached history;
oversized required control documents still prevent export. Larger raw evidence is
streamed for hashing and indexed. Redacted
shared copies need separate identities; export never replaces frozen originals.

Generation fixes the snapshot, creates JSON, renders reports, builds the index,
validates the bundle and uses the existing Apps no-replace directory publisher.
The reader rejects duplicate artifact IDs and duplicate bundled locations before
checking file digests, so a later entry cannot hide an earlier invalid checksum.
The reader also rejects absolute or escaping source locators; it does not open
additional source roots while validating an offline bundle.
Existing destinations survive every failure. Post-rename directory-sync failure
returns `uncertain` with the same export ID and visible output path: inspect it with
`read_bundle` before retrying. Atomic visibility and durability retain the platform
limits of [Apps publication](apps-output.md).

## Validation scope

`tests/apps/test_result_delivery.py` covers PASS/FAIL, missing final, baseline retention,
damaged evidence/code, both binding paths, usage, invalid ratios, archive authority,
source changes, writer locks, publication faults, hostile text/paths and historical
adapters. Project and Benchmark lifecycle tests exercise automatic export through
real CPU subprocess fixtures and retry without remeasurement. These verify software
behavior, not accelerator performance. RFC adoption, a future service-reuse producer
and real campaign performance acceptance remain separate.
