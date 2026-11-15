# D008 wave-2 ownership decision

Status: **Adopted for the five entries below**. Decision date: **2026-11-14 Asia/Shanghai**.

## Authority and scope

**RSI-master** names the architecture-coordination role delegated by the requesting maintainer, **Dong1017 (xinwen dong)**, to the assistant coordinating these changes. It is not an additional GitHub account, an independent reviewer, an extra approver, or a statement of legal repository ownership. Under that delegation, RSI-master makes and records the architecture choice rather than asking reviewers to select an owner.

This file is the citable record of the five decisions adopted under that delegation for Issues [#414](https://github.com/InferMatrixLab/InferRSI/issues/414) (B01 / PR #422) and [#413](https://github.com/InferMatrixLab/InferRSI/issues/413) (OBS / PR #425). It makes no blanket acceptance claim for the other proposed entries in [function-owners.md](function-owners.md).

Architecture adoption is **not** reviewer `APPROVE`, implementation acceptance, permission to merge, a gate-policy exception, or evidence that tests passed. Reviewers verify the boundary, correctness and evidence against the actual head; their independent PR decision remains separate.

## Benchmark sampling

**Adopted:** `collect_samples` belongs to **Benchmark sampling**. Benchmark owns sampling order, timing records and artifact hashes. Request transport remains the caller-injected `request(item, path)` callback; it does not become a Harness or model dependency of Benchmark.

Issue #414 explicitly assigns this sampling to Benchmark. The implementation is `benchmark/sampling.py`; the artifact hasher equivalence is pinned by `test_sampling_sha256_matches_the_infra_hasher`. Retaining existing protocol output does not confer ownership of UI presentation or of a caller-owned record's lifecycle.

## Snapshot port

**Adopted:** **Harness** owns the required keyword-only `snapshot(repo, exclude) -> dict` port contract; **Apps legacy** owns the binding; **infra/targets** owns the Git identity implementation. Harness has **no concrete default** for this port and does not hold a copy of the target implementation.

This preserves the Issue #414 split: execution facts in H, composition in Apps, implementation behind an injected port. It does not restore an H-to-infra edge. Existing compatibility disclosure for out-of-tree direct H callers remains applicable; this record does not erase it.

## Dashboard workflow

**Adopted:** `command_state`, `run_workflow` and `validation_progress` belong to **Apps views**. They project caller-loaded records into display state/counters. Their output is not a Benchmark verdict or a claim-acceptance decision.

## Profile records and overview

**Adopted:** profile attachment, factual record encoding, bounded single-trace overview generation, fixed-byte integrity checks and digest-based record reads belong to **Harness records**. UI projections and route decoration belong to **Apps views**. In particular, constructing an `events_url` for the live server is not an H responsibility.

This explicitly refines Issue #413's broad wording that dashboards/timelines/templates move to Apps: a persisted factual record and its bounded overview remain H record content, while the presentation and URL are Apps concerns. This is an explicit split, not a claim that the issue wording already made the distinction verbatim. Bounding events/lanes within one trace does not authorize H to rank candidates, runs or claims or to generate verdicts.

The route decoration is to be moved into Apps in PR #425 while preserving stored bytes, digest verification and the external view response. This record does not by itself assert that the implementation or validation has finished.

## Pre-profile searches

**Adopted:** `pre_profile_searches` belongs to **Apps views**. It combines profile facts with an existing search/ledger read model for display. Its annotations are not a new claim-evidence verdict.

## Integration constraints

The four-module dependency direction remains unchanged: Apps assembles the peers; H records do not import K or Apps. Pure knowledge context assembly belongs to K; explicit capture orchestration belongs to Apps; H retains actual delivered facts/bytes and their integrity. The #428 capture/navigation features must be preserved when OBS absorbs the newer main layout, rather than restoring an `observability` forwarding package or dropping retrieval metadata.

Implementation acceptance remains in the governing issues: old-run behavior and byte evidence for #414; fixed-record CLI/offline/live/trace behavior, H closure, resource packaging and disappearance of `observability/` for #413. `overall isolation_complete` remains false. None of those evidence requirements is waived here.
