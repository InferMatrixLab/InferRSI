# K/H/B + Apps contracts v1

Status: **Proposed**. This directory is the P0a contract root: documentation, JSON Schema, fixtures, and Decisions only. It is not maintainer acceptance, and it is not a runtime implementation.

Normative public sources, in conflict-priority order:

1. Issue #387 body, including section K: https://github.com/InferMatrixLab/InferRSI/issues/387#k-t115-contract-errata
2. D023 and T36–T40 errata: https://github.com/InferMatrixLab/InferRSI/issues/387#issuecomment-6785139079
3. Absorption of the four review points: https://github.com/InferMatrixLab/InferRSI/issues/387#issuecomment-6785143900
4. #371 cross-reference: https://github.com/InferMatrixLab/InferRSI/issues/371#issuecomment-6785144030
5. t108-v4 seven volumes (foundation; section K and 6785139079 win on conflict), on #387: 6784351533, 6784351520, 6784351492, 6784353963, 6784353989, 6784353899, 6784354043

P0b still requires a formal architecture review before K01. H01 creates a new local SQLite RunStore; it does not migrate `MemoryArchive`. Completing the whole Apps assembly is not a prerequisite.

## Files in this directory

- [CURRENT-DESIGN.md](CURRENT-DESIGN.md) — D001–D019, boundaries and ports
- [SCHEMA-AND-SEMANTICS.md](SCHEMA-AND-SEMANTICS.md) — encoding rules V01–V35
- [DTO-FIELD-INDEX.md](DTO-FIELD-INDEX.md)
- [D008-FUNCTION-OWNERS.md](D008-FUNCTION-OWNERS.md)
- [D020-D022.md](D020-D022.md)
- [D023.md](D023.md) — bounded errata (prepare closure, code digest, DeliveredContext, primary claim, disconnect replay)
- [GATE-STORE-AND-FIRST-PRS.md](GATE-STORE-AND-FIRST-PRS.md) — gate policy, RunStore candidate, and first PRs (P0b is not accepted here)
- [ACCEPTANCE-T01-T40.md](ACCEPTANCE-T01-T40.md)
- [FIGURES-ALL.md](FIGURES-ALL.md) and [diagrams/](diagrams/) — eight mermaid figures
- [schemas/contract-v1.schema.json](schemas/contract-v1.schema.json) and [schemas/INDEX.json](schemas/INDEX.json)
- [fixtures/README.md](fixtures/README.md) — historic t108-v4 golden bytes versus current D023 vectors
- [fixtures/d023-conformance-cases.json](fixtures/d023-conformance-cases.json) — T36–T40 specification vectors, not executed tests
- [fixtures/execution-spec-d023.json](fixtures/execution-spec-d023.json) — current `CommandStep.expected_code_sha256` example

This PR does not move source, change hard-gate implementation, or implement CLI, Apps assembly, or worker startup.
