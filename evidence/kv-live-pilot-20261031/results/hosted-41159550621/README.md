# First bounded live attempt: incomplete comparison

This directory preserves the first and only attempt of the frozen synthetic CPU
editing pair in [Issue #248](https://github.com/InferMatrixLab/InferRSI/issues/248).
[Run 41159550621, attempt 1](https://github.com/InferMatrixLab/InferRSI/actions/runs/41159550621)
finished on 2026-10-31 at 02:22:56 UTC. The workflow completed successfully;
both experimental arm grades are **INCONCLUSIVE**. There is no comparative
performance, knowledge-efficacy, vLLM-conformance or service result.

## Observed outcome and limits

- Preflight reports `prepared`, with staging, isolation, cleanup, runtime and
  scripted replay completed. These are control outcomes, not a live result.
- A2 execution is `failed`. One request slot was consumed; its completion is
  unresolved and usage is `null`. A consumed slot does not establish
  per-request gate authorization, HTTP delivery, provider processing or a model
  response.
- Only unchanged baseline revision 0 and its receipt were retained for A2.
  There is no final candidate or retained tool feedback. A3 is `not_started`
  and consumed no slot.
- Both arm grades are `INCONCLUSIVE: missing_or_invalid_artifact`. The grade
  evidence contains descriptors for 77 semantic and 17 performance rows per
  arm, but no observed semantic checks, semantic outputs or performance
  outputs. Missing observations are not zero-duration measurements or passes.
- The public artifacts do not retain the private worker result reason or
  provider-attempt detail. The failure cause and request delivery remain
  unknown. This archive does not reconstruct missing evidence from a rerun.

## Cost evidence

`cost.json` binds the frozen plan, original execution projection and immutable
action-time PR/day ledger commits. USD 162.72 is the reserved/claimed ceiling,
**not an observed bill**. `actual_cost_usd` is `null`; no authoritative usage or
billing receipt was retained. Do not substitute zero or the reservation for
actual cost, release the reservation from this archive, or infer retry authority.

## Exact source and original artifacts

- Executed source: [3ece458ceaa92c5dad8d8e0b1e782a6961400b96](https://github.com/InferMatrixLab/InferRSI/commit/3ece458ceaa92c5dad8d8e0b1e782a6961400b96),
  tree `bf3f8051e3ed3a51cc75e87f3bd49359d0539f1e`.
- Frozen [authorization comment](https://github.com/InferMatrixLab/InferRSI/issues/248#issuecomment-6537438741):
  plan SHA-256 `b66130352cce6fb6201561d3a026a7a78d800ac0f84ecb899f57a0906ffa4767`.
  Its original snapshot includes the 63-file dependency map, actor/public-input
  manifests, workload/oracle pins and prior model-free actor qualification.
- Execute artifact `kv-live-41159550621-1`, ID `13026626778`, 9,985 bytes,
  SHA-256 `33538429882da7dc522290d8a2691ccd5ee1266bc54ceb6fcf6da32a4658a4b9`.
- Grade artifact `kv-final-grade-41159550621-1`, ID `13025304718`, 15,254 bytes,
  SHA-256 `491990426fbfccb956aff8ba1a6c9b446d1169b6186432948f6b91ed39ffd511`.

The two ZIPs are the original downloaded bytes. `execute/` and `grade/` contain
their nine exact members, including the two identical authorization snapshots.
`manifest.json` records source/run binding, hashes, artifact metadata and
verification limits. Projection fingerprints use canonical JSON; file SHA-256
values identify the original formatted file bytes. Those are distinct hashes.

## Retention and privacy boundary

The exact staged ZIPs, all nine members and new manifests were inspected before
publication. They contain bounded public projections, public source/authorization
and missing-output evidence; no credentials, arbitrary environment logs, raw
provider responses or private worker logs are included. This clearance applies
only to these exact bytes, not to a general-purpose redaction mechanism.

Archiving used byte/hash, ZIP-integrity and metadata checks only. It did not
execute the candidate, call a model, rerun tests, dispatch another workflow,
change the frozen plan or mutate a ledger. Earlier evidence remains unchanged.
The archive commit adds evidence data only; it does not change source or main.

Agent-assisted provenance: Codex / gpt-6-astra [effort=xhigh], evidence retention;
independent byte/privacy review by the separate actor-isolation reviewer.
