# D023 — Five implementable revisions (P0a contract errata)

Status: **Proposed**. This volume is a bounded errata over the existing seven-volume baseline, not a second parallel design. The seven volumes remain the foundation; where they conflict, this volume wins.

Sources:

- [The #387 section-K version this errata corresponds to (comment 6785139079)](https://github.com/InferMatrixLab/InferRSI/issues/387#issuecomment-6785139079)
- [#387 t108-v4 specification index and section K](https://github.com/InferMatrixLab/InferRSI/issues/387#t108-v4-spec-index)
- [zengchuang's four handoff / CLI comments](https://github.com/InferMatrixLab/InferRSI/issues/387#issuecomment-6784446113)
- [#371 full design review, five items](https://github.com/InferMatrixLab/InferRSI/issues/371#issuecomment-6785041649)
- [Run-output special item (kept separately; full compatibility with every old output layout is not required)](https://github.com/InferMatrixLab/InferRSI/issues/371#issuecomment-6778800099)

Coverage: the public #387 section K and this volume (the same version as comment 6785139079) take priority over older t108 wording.

---

## D023-1 Prepare closure bytes, resource entries, and the final locator

`prepare` still does not write to disk, occupy budget, or start a process. In-process delivery **must**, in addition to the `PreparedEvaluation` object, include both of the following:

1. The canonical bytes of the protocol frozen for this call.
2. A read-only entry (bytes or a stream) to the resource closure, keyed by role. Existing, verifiable resources may reuse an existing reader. A newly generated protocol must not supply only an as-yet-unresolvable `ArtifactRef`.

Under a trusted, explicitly injected `StorageConfig`, Apps allocates the final location, then calls B's pure `encode`/`validate` (which may accept an already-allocated location) to produce and check the final prepared canonical bytes before archiving. Apps does not rewrite B's rules. B does not depend on Apps storage routing and does not store bytes itself. If any required resource, check, or archive step fails, there is no valid `PreparedRef`. After a complete commit, a new process can read using only the fixed Ref and the same configuration.

Identity recomputation still follows projection P: only the `location` of an outer, schema-declared `ArtifactRef` is stripped. **It is not true that an arbitrary relocation leaves `prepared_id` unchanged.** If the canonical bytes of the protocol object or of a resource description itself change because of an internal field, the corresponding sha and `prepared_id` are recomputed under the original rule. Committed bytes are immutable.

Machine schema: `PreparedEvaluation` gains no storage-location or archive-handle field. The final location appears only in the existing `ArtifactRef` on `protocol` / `resources[].artifact`.

**Acceptance: T36.**

## D023-2 The frozen worker code digest must reach H before start

`OperationRecipe.code_sha256` is the frozen expectation. P0a **selects** the default path: add a nullable `expected_code_sha256` on `CommandStep`.

- In evaluation mode (`prepared_ref` non-null) the field is **required and must equal** that frozen value. `OperationRecipe.code_sha256` is already a required non-null `Sha256` in the schema, so there is no third case in which “the recipe omitted a code digest,” and evaluation-mode `expected` is therefore not written as a nullable free choice.
- In ordinary command mode, per V05, the field is `null`. If, at spec time, it is non-null, or in evaluation mode it is `null` or non-null but not equal to the frozen recipe, the result is `InvalidExecutionSpec`: no start, no record, and it must not be called T37. A missing required key is a schema-layer rejection; a schema validator must not be equated with a runtime `InvalidExecutionSpec` or `PublicError`.
- Apps maps the value verbatim from the fixed `prepared.recipe` and must not rewrite or infer it.
- H computes the actual entry bytes and checks them before start; it does not import B.
- Code-identity scope is a supported entry or package; **the entire interpreter is not archived**.

Machine schema: `CommandStep.expected_code_sha256` is always present (newly required). Its type is `null` or a 64-digit lowercase-hex `Sha256`. Mode and equality constraints are borne by V32; the schema does not pretend to express cross-field equality.

If a later implementation instead uses a versioned H read-only binding projection to read the same expectation from the fixed prepared object, **that equivalence must be stated in the same contract revision**, and the implementation must not record only the actual observation without checking the expectation. This volume does not permanently forbid every path other than one DTO field (see the exclusions below).

**Acceptance: T37.**

## D023-3 DeliveredContext: bytes and commit first, valid Ref after

`ContextProvider.collect` must not return a valid `ArtifactRef` that has not yet been committed. Default path: Apps returns a `DeliveredContextDraft` — items, selection, omissions, limitations, bytes or a stream, and the intended logical location and digest. After H finishes retention with its own capture and commit, it **seals** the final `DeliveredContext` and only then writes the generation manifest. Calling a capture port defined by H is allowed, but the writer is still H. Apps does not write H's RunStore directly.

Machine schema: `DeliveredContext` is a **sealed, committed** delivery record; its `artifact` may point only at already-retained bytes. The pre-commit `DeliveredContextDraft` is a **process-local** value type. It is intentionally **not** a JSON `$defs` entry, and it is not given a fabricated serializable-stream DTO shape. Its bytes or stream are in-process objects, not a schema payload.

**Acceptance: T38.**

## D023-4 Primary-claim check order and AppsResultV1

P0a documents and the schema align with D022: `AppsResultV1` must include `primary_claim_id`, `primary_scope`, `exit_code`, and `error`, and must keep inner/outer Ref and `admission` consistent. `assess` must be given an exact `(primary_claim_id, primary_scope)`.

After a legal fixed protocol has been read, **first** check the requested key with B's public read-only claim-key capability or an explicit business-free projection, and finish that decision before calling the assessor:

- The key is not in the frozen protocol, or no legal primary key was provided → `InvalidRequest` / exit 2; the assessor is not called and no assessment is written.
- The key is in the protocol, but the B result omits it → `AssessorError`-class **result-contract error** / exit 2 (D022 maps other `PublicError` values, including `AssessorError`, to `error` / 2). Apps does not fill in the claim or mis-report it as a caller argument error.
- Legal complete result: archive failure takes priority (exit 6; an in-memory result may be kept, but `assessment_ref` must be `null`). On success, return 0 / 8 / 9 for the selected claim and leave other claims and scopes unchanged.

Machine schema: the four `AppsResultV1` fields are all required (nullable, but must be present). `AppsAssessRequest.primary_scope` / `primary_claim_id` are required `Id` values.

**Acceptance T39:** on top of T35, add the two rows “key not in the protocol” and “key in the protocol but omitted from the result,” each with a unique outcome.

## D023-5 CLI attempt save and disconnect replay

`AppsExecuteRequest.attempt` is required; `execute` **no longer** calls `allocate_attempt` itself. `StorageConfig` is injected by a trusted host or an explicit `--storage-config` and **does not enter** any `Apps*Request`.

First supported path: Python or the host first calls H `allocate_attempt`, **saves the complete `AppsExecuteRequest` before execution**, and then hands that file to the CLI. If a later revision promises a closed CLI-only loop, a separate entry for obtaining that file can be defined then; P0a does not grow the command set. K01 / H01 still do not implement the CLI.

Machine schema: `AppsExecuteRequest.attempt` is a required `AttemptContext`. The `StorageConfig` definition exists but is not referenced by any `Apps*Request`.

**Acceptance T40:** same RunStore, same saved request. After the first submit, the response is lost; replay returns the original `RecordRef` (already complete) or `RecoveryRequired` (state unknown). No new allocation, and no extension of deadline or budget. Disconnect replay **must reuse the original attempt and the original request**. A different request, or a rerun past the deadline, must not be described as the same replay.

---

## Explicitly not part of this errata

- Any internal location change leaves `prepared_id` unchanged.
- A code digest may be implemented only through one DTO field; equivalent projections are forbidden.
- The first-wave `prohibited_first_wave` list is a permanent ban, or a shell→Apps edge is permanently allowed without its own review.
- Because an illustrative tree omits `views/__init__.py`, packaging is already broken.
- Disconnect replay is interpreted as forbidding reuse of the original attempt.
- Locating or extracting bytes in `collect_candidate` is upgraded to a proven Apps scoring overreach.

## Boundaries and invariants

See [README.md](README.md) for repository-wide status and dependencies. In particular: P0b's exact gate policy still requires formal architecture review before K01; H01 creates a new local SQLite RunStore and does not migrate the test `MemoryArchive`; the full Apps implementation is not a prerequisite; the legacy `run` 0 / 1 / 2 contract and existing entry compatibility are not withdrawn; this volume adds no permanent gate exemption.

## Schema impact (summary)

| Location | Change | Semantic check |
| --- | --- | --- |
| `CommandStep` | New required `expected_code_sha256` (`null` ∨ `Sha256`) | V32 |
| `AppsExecuteRequest` | `attempt` remains required; meaning fixed as pre-allocated | V35 |
| `AppsAssessRequest` / `AppsResultV1` | The four primary-claim fields are required | V34 |
| `DeliveredContext` | Documented meaning = committed and sealed; the draft is not in the schema | V33 |
| `PreparedEvaluation` | No field change; in-process closure delivery is outside the object | V31 |
| Definition count | 106 → 106 (no new definition) | — |

`$id` stays `urn:inferrsi:design:contract-v1`. This volume is a Proposed revision of the same design library, not a second parallel schema. Machine definitions are still validated by selecting an explicitly named `$defs` entry; validating the empty library root is not a pass. The only field-set addition is on `CommandStep`; everything else is a required-flag or semantics tightening with no field change.
