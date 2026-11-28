# Harness preparation binding before registration

The Harness evaluation path checks declarations before registering an attempt.
`inferrsi.harness.executor.verify_prepared_binding(spec, artifact_reader)` returns a
`FixedPreparation` projection or raises a Harness `PublicError`. The spec must
first pass `execution_service.validate`'s static shape checks; `execute_attempt`
performs both checks in that order. Ordinary command mode reads no preparation.

The projection's `read_prepared_binding(ref, reader)` port obtains a binary stream through
`reader.open(ArtifactRef)`, closes it, bounds reads by the declared size plus one
byte, and independently checks size and SHA-256. Missing bytes or a missing
reader produce `ArtifactUnavailable`; changed bytes or noncanonical JSON
produce `ArtifactIntegrityError`. Unknown host programming errors propagate.
`project_prepared_binding(bytes)` is pure: it parses the canonical v1 envelope and validates the
fields used by Harness. It does not read a protocol, resolve an entry or start a
process. A schema version other than v1 is explicitly unsupported.

Binding compares the semantic prepared ID, protocol digest, operation and scope
with the fixed preparation. Disagreement is `IdentityMismatch`. It also checks:

- Candidate kind and role, a frozen expected candidate ID/hash/format when
  present, and the supported `captured-sha256@1` or `expected-sha256@1` identity
  rule. An unknown rule/revision is `UnsupportedRuleVersion`. The expected rule
  requires a declared expected input hash even without a frozen candidate.
- A non-null expected code digest on every evaluation step, matching the frozen
  recipe. This is an expected declaration, not an observed entry-code hash.
- One worker step preserving runtime role, entry kind/name/revision, all output
  declarations, and arguments with whole-argument `{input:role}` / `{output:role}`
  expansion. Inputs may use caller-chosen materialized paths; arguments must
  match those paths. Paths are relative to the attempt directory (`cwd="."`),
  and input/output paths must not overlap. Required frozen capabilities cannot
  be dropped; additional declared capabilities remain subject to admission.

Malformed or conflicting declarations are `InvalidExecutionSpec`. For a fresh
request these refusals precede `RunStore.claim`: neither attempt nor record is
registered. Existing request state is handled after static field checks and
before preparation IO by the [replay contract](harness-evaluation-replay.md).
The public projection does not interpret candidate formats, grading rules,
evidence requirements or scores, and does not recompute Benchmark's semantic
prepared ID. The fixed ArtifactRef authenticates the preparation bytes; Apps
performs the separate archived-protocol binding through its canonical
`inferrsi.apps.handoff.bridge.verify_protocol` port.

The D023 conformance vector is kept separately under
`tests/fixtures/harness-prepared-binding/`. It adds the frozen code declaration
and a null step timeout without rewriting historical fixtures. Its canonical
bytes must agree between the Apps binder and Harness `request_digest`.
The vector is documentary; its historical code pin is not an available worker.

Targets without an explicit `module_root` keep valid evaluation-mode execution
unsupported before registration. A configured source target performs the separate
[post-registration entry check](harness-entry-verification.md) (T37). The
[original-limit/replay path](harness-evaluation-replay.md) covers the next
delivery unit, whose complete CPU acceptance retains its launch prerequisite.
Declaration checks alone do not establish
production CPU acceptance or completion of the governing Harness or Apps Issues.
