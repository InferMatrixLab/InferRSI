# Fixtures: historic baseline bytes and current D023 vectors

Status: **Proposed**. Documentation fixtures only. Nothing here is produced by a runtime test, and no case asserts that `prepare`, `execute`, `assess`, or any test runner was executed.

This directory holds two different things and they must not be conflated:

| Path | Nature | Schema relation |
| --- | --- | --- |
| `fixtures/t108-v4/` | **Historic BASELINE / HISTORICAL golden byte vectors**, copied unchanged from the reviewed t108-v4 handoff | Validated against the **baseline** 106-definition library. **Not** D023-current examples; several of them no longer validate as-is. |
| `fixtures/execution-spec-d023.json` | Current D023 `ExecutionSpec` example | Written for the D023 library (`CommandStep.expected_code_sha256` required). |
| `fixtures/d023-conformance-cases.json` | Document vectors for T36–T40 | Current; fixed example digests, not computed values. |

## Why the baseline bytes are preserved, not rewritten

`D023-2` adds a required, nullable `CommandStep.expected_code_sha256` to the schema. That field participates in the canonical `ExecutionSpec` bytes and therefore in `request_digest` (`V32`). Every historic `ExecutionSpec`-shaped byte sequence in the baseline — `execution-spec.json`, the `negative-schema-cases.json` spec case, the `semantic-conformance-vectors.json` spec, and the recorded `request_digest` values that reference them — was produced before the field existed.

Silently regenerating those bytes would:

- change `request_digest` for requests whose historic value is already quoted by `MANIFEST.json` and by the record/prepared/assessment fixtures;
- make the baseline `MANIFEST.json` describe bytes that no longer exist;
- erase the evidence that D023-2 is a deliberate, reviewed contract change rather than a drift.

So the historic bytes stay exactly as generated, and the new D023 form is emitted as a **separate** file. The baseline `MANIFEST.json` is kept beside the bytes it describes, and is labelled historic here and in the manifest's own `scope` field.

## Historic baseline verification contract

`fixtures/t108-v4/MANIFEST.json` records, for each of its 22 entries, the exact `bytes` and `sha256` of the file and the semantic ids derived from it. The coordinator validates the copy by:

1. comparing each file in `fixtures/t108-v4/` **byte-for-byte** against `MANIFEST.json` (size and sha256, with no canonicalization, no re-encoding, and no trailing-newline normalization);
2. confirming the manifest's own `protocol_digest`, `prepared_1_id`, `prepared_2_id`, `request_digest`, and `assessment_id` against the referenced documents;
3. validating the *baseline* schema from already-reviewed input — **not** by pretending these fixtures pass the D023 schema unchanged.

Known, expected mismatches against the D023 library (not defects):

- `fixtures/t108-v4/execution-spec.json` has no `CommandStep.expected_code_sha256`; it is a pre-D023 spec and its `request_digest` (`sha256:34793d13…ed5c`) is the pre-D023 value.
- Any baseline vector embedding that spec inherits the same status.

The historic fixtures are immutable. Corrections go into a new file, never into `fixtures/t108-v4/`.

## Text fixtures with non-ASCII and control content

`fixtures/t108-v4/candidate.txt` and `candidate-2.txt` are raw UTF-8 text, not JSON. `fixtures/t108-v4/codec-strings.json` and `codec-string-vectors.json` intentionally embed U+007F (DEL), U+2028, U+2029, a decomposed `e`+U+0301, and a non-BMP emoji. These are the vectors; do not "clean" them. Byte equality with the manifest is the acceptance criterion.

## Current D023 example

`fixtures/execution-spec-d023.json` is the historic `execution-spec.json` with **only** `expected_code_sha256` added to its single `CommandStep`. It is in evaluation mode, so the value is the frozen `code_sha256` from the historic protocol recipe (`prepared.json` → `recipe.code_sha256`):

```
ba351e8f96c162ed9c32309f24b1d2d75d11a7369168571ebbb0a79d13315332
```

It is canonical `inferrsi-json-v1`: ASCII key ordering, UTF-8, no BOM, no spaces, no trailing LF. All other fields are byte-identical to the pre-D023 spec, including `request_digest`'s other inputs; the file deliberately does **not** carry a `request_digest` value, since the new digest must be recomputed over the new canonical bytes.

**The coordinator computes the canonical byte hash for this file and supplies it for the manifest.** No digest in this document or in the file is a claimed computed value for the D023 spec.

## T36–T40 are specifications, not executed integration tests

`fixtures/d023-conformance-cases.json` and section 3 of `ACCEPTANCE-T01-T40.md` describe T36–T40. They are **runtime specifications**: each states explicit input facts and the single required outcome. None of them has been executed. Schema acceptance is not test acceptance, and no claim here is made that any implementation already satisfies them.

## Normative and source references

Local specification files:

- [`../README.md`](../README.md) — contract set index and status
- [`../CURRENT-DESIGN.md`](../CURRENT-DESIGN.md) — D001–D019 and boundaries/ports
- [`../SCHEMA-AND-SEMANTICS.md`](../SCHEMA-AND-SEMANTICS.md) — D002/D017, canonical encoding, V01–V35
- [`../D023.md`](../D023.md) — P0a errata: T36–T40 inputs and schema deltas
- [`../D020-D022.md`](../D020-D022.md) — D020–D022 decisions
- [`../D008-FUNCTION-OWNERS.md`](../D008-FUNCTION-OWNERS.md) — function ownership
- [`../GATE-STORE-AND-FIRST-PRS.md`](../GATE-STORE-AND-FIRST-PRS.md) — D009/D018, D012-r2 RunStore, D019 first PRs
- [`../ACCEPTANCE-T01-T40.md`](../ACCEPTANCE-T01-T40.md) — T01–T40 unique outcomes
- [`../FIGURES-ALL.md`](../FIGURES-ALL.md) — figures
- [`../schemas/contract-v1.schema.json`](../schemas/contract-v1.schema.json) — Draft 2020-12 library, 106 named definitions
- [`../schemas/INDEX.json`](../schemas/INDEX.json) — machine-derived definition index
- [`../DTO-FIELD-INDEX.md`](../DTO-FIELD-INDEX.md) — machine-derived field index
- [`d023-conformance-cases.json`](d023-conformance-cases.json) — T36–T40 document vectors
- [`execution-spec-d023.json`](execution-spec-d023.json) — current D023 spec example
- [`t108-v4/MANIFEST.json`](t108-v4/MANIFEST.json) — historic baseline byte manifest

Public sources:

- [InferRSI #387 — spec index and the K section / D023 version (comment 6785139079)](https://github.com/InferMatrixLab/InferRSI/issues/387#issuecomment-6785139079)
- [InferRSI #387 — baseline schema snapshot (comment 6784351492)](https://github.com/InferMatrixLab/InferRSI/issues/387#issuecomment-6784351492)
- [InferRSI #387 — baseline schema snapshot (comment 6784353963)](https://github.com/InferMatrixLab/InferRSI/issues/387#issuecomment-6784353963)
- [InferRSI #387 — handoff / CLI comments](https://github.com/InferMatrixLab/InferRSI/issues/387#issuecomment-6784446113)
- [InferRSI #371 — full design review, five items](https://github.com/InferMatrixLab/InferRSI/issues/371#issuecomment-6785041649)
