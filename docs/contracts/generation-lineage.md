# Same-Store generation lineage for CPU evaluation

The restricted profile in [#584](https://github.com/InferMatrixLab/InferRSI/issues/584)
admits an evaluation of an already generated candidate through the existing
`Harness.execute` port. The host still saves the complete request and allocates
a distinct evaluation attempt. Apps forwards the original `generation_record_ref`;
H owns authorization, input capture, execution and replay. No public DTO or
record field is added.

This profile requires the same authorized RunStore and the existing trusted
local CPU evaluation target with its module root. It does not add scheduling,
automatic retries, another backend or budget-policy support.

## Admission before registration

After static request checks, H consults any existing registration first. Only
a fresh request reaches fixed preparation, target and lineage validation.
Public `execution_service.validate` has no Store authority and continues to
refuse non-null lineage. Use `Harness.execute` for Store-backed admission.

H reads the generation's specified record version through its own Store and
compares the complete RecordRef. It requires the same run and owner, a successful
finished ordinary generation, known side effects and a sealed
[original-bounds snapshot](generation-bounds.md). Historical generations without
that snapshot remain usable by their original ordinary/replay paths, but cannot
authorize a new lineage evaluation. There is no backfill or `current` fallback.

| Fixed source | Association checked by H |
| --- | --- |
| Original bounds and generation record | Original attempt/run/owner and request digest agree. The immutable generation-plan descriptor already binds registration to that original digest. |
| Original plan Ref | Read the pre-sealed H generation-plan bytes from the fixed internal slot and verify their size, SHA and v1 shape. This is not the worker's output manifest. |
| Generation record's `generation_plan` BoundInput | Exactly one verified file capture for the generation attempt, with the original expected/actual plan SHA and equal retained bytes. Its captured object locator may differ from the original plan locator. |
| Plan `output_contract.candidate_role` | Exactly one available retained artifact with that role, the generation attempt, an observed step and the declared format schema. |
| Evaluation candidate input | Its artifact namespace, complete `source_ref`, source locator and expected SHA match that original artifact; the supported snapshot is `file-v1`. |

H independently verifies retained plan/candidate bytes before registering the
evaluation. It does not parse the worker's manifest, grade the candidate, or
authenticate worker-reported CandidateDescriptor metadata. Apps' existing
candidate collection owns that parsing contract. The H guarantee here is the
original retained artifact/byte association and the fixed execution facts.

## Original limits and capture

The original deadline must not already be expired. The evaluation deadline may
be earlier or equal, never later. Comparison preserves the Timestamp contract's
nanosecond precision and does not rewrite either timestamp or request identity.
The budget scope and policy must be identical to the original snapshot; normal
local target budget admission still applies. The full original budget remains
retained separately from admission, reservations and actual usage.

At actual input capture, the authorized candidate is opened again through H's
own Store. Unrelated inputs retain their configured reader. Capture independently
checks the actual bytes against the frozen input identity. A source changed
after validation produces the existing committed `started=false` binding refusal
before any worker runs; it is not relabeled as a pre-registration failure.

Manual-candidate evaluation (`generation_record_ref=null`) keeps its existing
path. Generation and evaluation records remain distinct, and the evaluation
record keeps the original generation Ref. Execution exit status remains a fact,
not a Benchmark claim verdict.

## Errors and replay

Fresh lineage refusals occur at `validate`, before a claim or worker start:

| Condition | Existing code |
| --- | --- |
| Malformed requested RecordRef | `InvalidExecutionSpec` |
| Foreign Store authority, unsealed/unsuccessful generation, missing historical bounds or expired original deadline | `UnsupportedOperation` |
| Unknown fixed record/version | `RecordNotFound` |
| Full Ref, run/owner, plan/candidate association, deadline or budget identity mismatch | `IdentityMismatch` |
| Damaged committed record | `RecordIntegrityError` |
| Missing/inaccessible retained source | `ArtifactUnavailable` |
| Damaged bytes or malformed retained metadata | `ArtifactIntegrityError` |
| Unsupported generation-plan major version or candidate snapshot rule | `UnsupportedSchema` / `UnsupportedRuleVersion` |

The existing registered-request table takes precedence. Reusing a registered
generation attempt ID with the evaluation's different digest therefore returns
`RequestConflict` at `claim`, as explicitly accepted in
[7087203358](https://github.com/InferMatrixLab/InferRSI/issues/584#issuecomment-7087203358).
It does not become a fresh lineage refusal. An identical-digest completed replay
returns its original RecordRef before reading sources or binding a target, even
after sources disappear, the target retires or time expires. Live/unknown
registrations retain `AttemptInProgress` / `RecoveryRequired`; no new attempt
or implicit rerun is introduced.

Apps output publication remains separate from H commit: publication failure
preserves the already committed evaluation Ref and its generation association.
Replaying the saved request can publish that original result later. No execution
or evaluation verdict is manufactured to fill an unavailable artifact.
