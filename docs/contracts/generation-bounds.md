# Internal original generation bounds

`inferrsi.harness.generation.prepare_generation` seals an approved context and
generation plan before execution registration. Its caller supplies the original
attempt, context request, candidate context and provider ports. It writes the
authorized RunStore and returns the ordinary execution specification; it does
not allocate an attempt, start a process or reserve a budget.

New preparations retain an internal original-bounds snapshot alongside the
generation plan's existing `request_digest` descriptor. The snapshot contains:

- Schema version, original attempt ID, run ID and owner.
- Original deadline and the complete declared budget, including policy, scope,
  dimensions and enforcement requirements.
- The fixed generation-plan reference and the existing execution request digest.

The snapshot and its checksum are part of the same immutable SQLite row and
transaction as the generation plan. A failed plan commit exposes no snapshot;
the separately committed delivered context retains its existing recovery rules.
The generation-plan bytes, its public ArtifactRef, returned ExecutionSpec,
request digest, execution-record fields and replay identity are unchanged.

## Internal reads and historical compatibility

Harness uses `RunStoreReader._read_generation_bounds(attempt_id)` internally.
It validates the checksum, attempt identity, original bounds shape, plan bytes
and fixed reference. It returns a fresh dictionary, or `None` for an absent plan
or a historical plan whose descriptor contains only its original request digest.
Storage failures raise `ArtifactUnavailable`; malformed or mismatching retained
metadata raises `ArtifactIntegrityError`, at `read_generation_bounds`. Neither
error is silently relabeled as a missing historical snapshot.

Historical rows are never backfilled. Repreparing the same historical request
uses its original plan and descriptor without updating either; a changed plan
or request digest still conflicts. Ordinary execution and completed-attempt
replay retain their existing behavior.

The checksum detects corruption within the trusted RunStore; it is not an
external source-authentication mechanism. The snapshot is internal metadata,
not a new public DTO, artifact location, admission result or spending record.
It introduces no deadline or budget policy for existing ordinary commands.

## Remaining capability

This retention slice does not enable generation-lineage evaluation. The current
generation-chaining refusal remains in place. Future admission must separately
verify the fixed successful generation, retained candidate association, original
deadline and budget policy. Missing historical bounds cannot establish those
facts and must fail closed for that future operation.
