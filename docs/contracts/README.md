# K/H/B + Apps contracts v1

This directory is the P0a contract root: human-readable design, JSON Schema Draft 2020-12, fixtures, and Decisions. Status: **Proposed**.

## Status and dependencies

Read this section once. Later files keep only local interface errors and acceptance boundaries.

- This pull request is documentation, schema, and fixtures only. It does not move `src/`, change the current hard gates, or implement P0b, K01, H01, H02, CLI, Apps assembly, or worker startup.
- These documents are specifications, not executed runtime tests. Schema validation is not acceptance of T01–T40.
- Merging this PR is not a check of the #387 acceptance boxes, and it is not acceptance of P0b or K01. P0b still requires a formal architecture review before K01. H01 creates a new local SQLite RunStore and does not migrate `MemoryArchive`. Completing the Apps assembly is not a prerequisite.
- This PR does not add `tests/` or `.github/` consistency guards. Schema self-check, the 106-definition count, the DTO field index, historic MANIFEST hashes (with the `fixtures/` → `fixtures/t108-v4/` mapping), and the current `execution-spec-d023.json` digest are review-time file checks. Whether a later gate-policy PR includes CI guards is a review item for that PR.
- Chinese text, U+007F, U+2028, U+2029, decomposed characters, and non-BMP emoji in `fixtures/t108-v4/` are frozen test-vector bytes, not documentation to translate or clean. Schema filenames, fixture data filenames, and historic golden bytes stay as they are.

## Normative sources (conflict order)

1. Issue #387 body, including section K: https://github.com/InferMatrixLab/InferRSI/issues/387#k-t115-contract-errata
2. D023 and T36–T40 errata: https://github.com/InferMatrixLab/InferRSI/issues/387#issuecomment-6785139079
3. Absorption of the four review points: https://github.com/InferMatrixLab/InferRSI/issues/387#issuecomment-6785143900
4. #371 cross-reference: https://github.com/InferMatrixLab/InferRSI/issues/371#issuecomment-6785144030
5. t108-v4 seven volumes (foundation; section K and 6785139079 win on conflict), on #387: 6784351533, 6784351520, 6784351492, 6784353963, 6784353989, 6784353899, 6784354043

Where they differ, [p0a-contract-errata.md](p0a-contract-errata.md) (D023) wins over earlier volumes.

## Reading order

1. This README — entry, status, priority, and file map
2. [current-design.md](current-design.md) — D001–D019 overview and ports
3. [p0a-contract-errata.md](p0a-contract-errata.md) — D023 bounded errata (T36–T40, V31–V35)
4. [schema-and-semantics.md](schema-and-semantics.md) — canonical encoding and V01–V35
5. [acceptance-criteria.md](acceptance-criteria.md) — T01–T40 unique outcomes
6. [figures.md](figures.md) and [diagrams/](diagrams/) — eight explanatory figures
7. [schemas/contract-v1.schema.json](schemas/contract-v1.schema.json) — machine fields (106 `$defs`)
8. [fixtures/README.md](fixtures/README.md) and the fixture files
9. Supporting decisions and indexes: [isolation-errors-and-cli.md](isolation-errors-and-cli.md) (D020–D022), [gate-policy-runstore-and-first-prs.md](gate-policy-runstore-and-first-prs.md), [function-owners.md](function-owners.md) (D008), [dto-field-index.md](dto-field-index.md)

## Files

| File | Purpose and retained IDs |
| --- | --- |
| [current-design.md](current-design.md) | D001–D019, boundaries and ports |
| [schema-and-semantics.md](schema-and-semantics.md) | Canonical encoding rules V01–V35 |
| [dto-field-index.md](dto-field-index.md) | Derived field index for the 106 definitions |
| [function-owners.md](function-owners.md) | D008 function ownership |
| [isolation-errors-and-cli.md](isolation-errors-and-cli.md) | D020–D022 isolation, errors, and CLI matrix |
| [p0a-contract-errata.md](p0a-contract-errata.md) | D023 bounded errata: prepare closure, code digest, DeliveredContext, primary claim, disconnect replay |
| [gate-policy-runstore-and-first-prs.md](gate-policy-runstore-and-first-prs.md) | Gate policy, RunStore candidate, and first PRs |
| [acceptance-criteria.md](acceptance-criteria.md) | T01–T40 unique outcomes |
| [figures.md](figures.md) and [diagrams/](diagrams/) | Eight mermaid figures; sources must match the FIGURES entry |
| [schemas/contract-v1.schema.json](schemas/contract-v1.schema.json) and [schemas/INDEX.json](schemas/INDEX.json) | Machine schema and definition index |
| [fixtures/README.md](fixtures/README.md) | Historic t108-v4 golden bytes versus current D023 vectors |
| [fixtures/d023-conformance-cases.json](fixtures/d023-conformance-cases.json) | T36–T40 specification vectors plus V32/SCHEMA spec-time cases |
| [fixtures/execution-spec-d023.json](fixtures/execution-spec-d023.json) | Current `CommandStep.expected_code_sha256` example |
| [fixtures/MANIFEST-d023.json](fixtures/MANIFEST-d023.json) | Current D023 example byte / `request_digest` documentation anchor |

## Former filenames

Ordinary human-readable documents use lowercase kebab-case. `README.md` is kept. Schema and fixture *data* filenames are unchanged.

| Former name | Current name |
| --- | --- |
| `CURRENT-DESIGN.md` | [current-design.md](current-design.md) |
| `SCHEMA-AND-SEMANTICS.md` | [schema-and-semantics.md](schema-and-semantics.md) |
| `DTO-FIELD-INDEX.md` | [dto-field-index.md](dto-field-index.md) |
| `D008-FUNCTION-OWNERS.md` | [function-owners.md](function-owners.md) |
| `D020-D022.md` | [isolation-errors-and-cli.md](isolation-errors-and-cli.md) |
| `D023.md` | [p0a-contract-errata.md](p0a-contract-errata.md) |
| `GATE-STORE-AND-FIRST-PRS.md` | [gate-policy-runstore-and-first-prs.md](gate-policy-runstore-and-first-prs.md) |
| `ACCEPTANCE-T01-T40.md` | [acceptance-criteria.md](acceptance-criteria.md) |
| `FIGURES-ALL.md` | [figures.md](figures.md) |
| `diagrams/387-1.mmd` | [diagrams/public-ports-and-primitives.mmd](diagrams/public-ports-and-primitives.mmd) |
| `diagrams/387-2.mmd` | [diagrams/execute-to-assess-handoff.mmd](diagrams/execute-to-assess-handoff.mmd) |
| `diagrams/387-3.mmd` | [diagrams/knowledge-read-and-internal-schema.mmd](diagrams/knowledge-read-and-internal-schema.mmd) |
| `diagrams/387-4.mmd` | [diagrams/legacy-run-v0-exit-codes.mmd](diagrams/legacy-run-v0-exit-codes.mmd) |
| `diagrams/387-5.mmd` | [diagrams/target-port-topology.mmd](diagrams/target-port-topology.mmd) |
| `diagrams/387-6.mmd` | [diagrams/end-to-end-handoff-and-replay.mmd](diagrams/end-to-end-handoff-and-replay.mmd) |
| `diagrams/387-7.mmd` | [diagrams/migration-overview.mmd](diagrams/migration-overview.mmd) |
| `diagrams/371-1.mmd` | [diagrams/apps-assembly-sequence.mmd](diagrams/apps-assembly-sequence.mmd) |

Unchanged data names: `schemas/contract-v1.schema.json`, `schemas/INDEX.json`, `fixtures/t108-v4/**`, `fixtures/execution-spec-d023.json`, `fixtures/MANIFEST-d023.json`, `fixtures/d023-conformance-cases.json`. Decision, validation, and acceptance IDs (`D001`–`D023`, `V01`–`V35`, `T01`–`T40`) stay in the body for traceability.
