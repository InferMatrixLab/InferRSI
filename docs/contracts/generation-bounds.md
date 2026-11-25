# Internal original generation bounds

`inferrsi.harness.generation.prepare_generation` seals an approved context and
generation plan before execution registration. Its caller supplies the original
attempt, context request, candidate context and provider ports. It writes the
authorized RunStore and returns the ordinary execution specification; it does
not allocate an attempt, start a process or reserve a budget.

New preparations retain an internal original-bounds snapshot alongside the
generation plan, in a separate internal retention slot. The snapshot contains:

- Schema version, original attempt ID, run ID and owner.
- Original deadline and the complete declared budget, including policy, scope,
  dimensions and enforcement requirements.
- The fixed generation-plan reference and the existing execution request digest.

The snapshot and its checksum occupy an immutable SQLite row committed in the
same transaction as the generation plan. A failed plan commit exposes no snapshot;
the separately committed delivered context retains its existing recovery rules.
The generation-plan bytes, its public ArtifactRef, returned ExecutionSpec,
request-digest descriptor, execution-record fields and replay identity are unchanged.

## Internal reads and historical compatibility

Harness uses `RunStoreReader._read_generation_bounds(attempt_id)` internally.
It validates the checksum, attempt identity, original bounds shape, plan bytes
and fixed reference. It returns a fresh dictionary, or `None` for an absent plan
or a historical plan with no bounds slot.
Storage failures raise `ArtifactUnavailable`; malformed or mismatching retained
metadata raises `ArtifactIntegrityError`, at `read_generation_bounds`. Neither
error is silently relabeled as a missing historical snapshot.

Historical rows are never backfilled. Repreparing the same historical request
uses its original plan and descriptor without updating either; an older sealing
caller can also reprepare a new plan using its unchanged descriptor. A changed plan
or request digest still conflicts. Ordinary execution and completed-attempt
replay retain their existing behavior.

The checksum detects corruption within the trusted RunStore; it is not an
external source-authentication mechanism. The snapshot is internal metadata,
not a new public DTO, artifact location, admission result or spending record.
It introduces no deadline or budget policy for existing ordinary commands.

## Remaining capability

Retention alone does not authorize generation-lineage evaluation. The separate
[same-Store CPU profile](generation-lineage.md) checks the fixed successful
generation, retained candidate association, original deadline and budget policy
before registration. Missing historical bounds cannot establish those facts and
remain a refusal for that operation. Ordinary execution and replay stay separate.
