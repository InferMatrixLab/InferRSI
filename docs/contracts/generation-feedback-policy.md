# Frozen generation feedback: opt-in profile

The restricted profile accepted in
[#586](https://github.com/InferMatrixLab/InferRSI/issues/586#issuecomment-7085395676)
checks the original proof references in `CandidateContext.allowed_feedback`.
It is separate from a search/loop controller and does not grade evidence.

## Host entry

`inferrsi.harness.executor.prepare_generation` keeps its existing required
arguments and accepts three keyword-only options:

| Option | Value |
| --- | --- |
| `feedback_policy_ref` | Optional existing `ArtifactRef` to canonical `CampaignPlan` v1 bytes approved by the trusted host |
| `feedback_record_refs` | Ordered sequence of existing fixed `RecordRef` values from the same authorized RunStore; empty by default |
| `artifact_reader` | Read-only `open(ArtifactRef)` port for the policy and original fixed prepared/protocol metadata |

With no policy Ref, existing calls retain their exact preparation identity,
specification and trusted-host behavior. Feedback authorization is **host
precondition, not proved by H**. Supplying source records without a policy is
an invalid new call.

With a policy Ref, H checks authorization before collecting context or asking
the candidate provider for a plan. A rejection at this point calls neither
provider and starts no worker.

## Authoritative mapping

The frozen policy has one `ScopedPrepared` per `validation_scope`.
`CampaignPlan.allowed_feedback` contains permitted **scope IDs**.
Within a permitted scope, the fixed `ProtocolV1.feedback_visibility` contains
permitted **check IDs** from its `required_evidence`. Unknown or ambiguous
bindings are refused rather than inferred.

For each source record, H reads the requested version through its own Store,
checks the entire RecordRef, run/owner, candidate parent and captured candidate
identity, and matches its original prepared/protocol to the policy. Prepared
and protocol byte and semantic identities are verified. Identity projection
strips only schema-typed ArtifactRef locations; Parameters remain semantic.

H resolves check IDs to actual `CheckObservation.evidence_refs`, matching the
attempt, operation, scope, checker/schema and frozen producer/control-domain
requirements. The original proof bytes must still be accessible and correct.
Every requested feedback Ref must equal one of these authorized Refs in full.
An alternate location with the same hash is not interchangeable. Whole
assessments, assessment summaries and arbitrary feedback documents are outside
this profile.

Scopes the policy does not grant, including final-only scopes, cannot supply
feedback even if their protocol exposes checks. H uses fixed record and policy
identities, not a caller's scope label. The policy author must split or exclude
a scope used for both feedback and final-only acceptance; H cannot detect an
unexpressed mixed use. Approval of the policy itself and the contents of other
text/material channels remain trusted-host responsibilities.

## Sealing and replay

H retains the original policy bytes at an existing Store object address and
adds an InputSpec with role `generation_feedback_policy` and path
`inputs/generation-feedback-policy.json` to opt-in specifications. Those bytes
are frozen rule metadata, not a whole assessment. Role/path collisions are
refused after the provider's plan is available; no worker or final plan commit
follows that refusal. Object retention alone does not publish a generation
specification: the normal generation-plan seal must succeed.

Only opt-in preparations add the original policy Ref and ordered source
RecordRefs to the preparation digest. Preserve that order and the complete
references when repreparing the same attempt. A changed Ref/sequence conflicts
with an existing delivery at `delivered-context-retention`; it cannot reuse
that delivery. Repreparation reads the already-retained policy bytes, while
the source records and required prepared/protocol/proof bytes remain subject
to fixed-reference verification. There is no fallback to `current`.
Retained-policy recovery requires a committed delivered-context row. If policy
object retention succeeded but context collection or delivery sealing failed,
repreparation still needs the original policy bytes through `artifact_reader`.

The generation manifest has no new fields. Opt-in specs include the policy
input in the normal request digest; existing specs and descriptors are not
rewritten. This change adds no check or attempt allocation to `Harness.execute`.
With the #564 replay path, executing the same registered specification returns
the original fixed record before fresh policy/input reads, target admission or
deadline checks. Missing or corrupt retained policy bytes do not authorize a
rerun. A changed request digest still conflicts before those fresh operations.
Repreparing a generation remains a separate operation with the fixed-reference
verification described above.

## Errors and limits

Policy refusals use existing `PublicError` codes at `validate`: invalid input
or a missing grant uses `InvalidRequest`; unknown major versions use
`UnsupportedSchema`; unsupported matching/snapshot rules use
`UnsupportedRuleVersion`; fixed identity/producer mismatches use
`IdentityMismatch`; missing records use `RecordNotFound`; unavailable or damaged
bytes use `ArtifactUnavailable` or `ArtifactIntegrityError`. Store record damage
keeps `RecordIntegrityError`. Reader authorization errors retain their existing
code. No new verdict is introduced.

Changed preparation identity retains `RequestConflict` at
`delivered-context-retention`. Policy retention failure uses
`ExecutionPersistenceError` at `generation-seal`, with `started=false` and no
new valid generation spec.

H does not authenticate the person who approved the policy, scan free text for
final-only information, or add scheduling, retries or branching. A policy-role
input by itself is not an attestation that a caller used this opt-in entry.
Control records in tests are distinct from production-worker evidence; CPU
generation correctness does not establish a task or service-performance gain.
