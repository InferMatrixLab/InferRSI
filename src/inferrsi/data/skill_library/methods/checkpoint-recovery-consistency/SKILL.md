---
name: checkpoint-recovery-consistency
description: 'Assess distributed checkpoint recovery using DLRover memory agreement, persistence completion and replica transport, and NVIDIA Resiliency Extension complete-iteration selection. Distinguish worker, host and replica loss; separate queued saves, publication, application-state validity and durable recovery.

  '
---

# Checkpoint Recovery Consistency

Status: candidate; source-inspected contracts, no save-throughput, recovery or
failure-injection result. [Pinned sources and limits](references/sources.md).
Reading does not authorize launchers, failure injection or checkpoint loading.

## Scope

RAM / Host → Configure, Verify; SSD / Storage → Configure, Verify;
Communication / Network → Diagnose, Configure, Verify for cross-rank agreement
and remote replicas; OS / System → Diagnose for launcher/helper lifetimes.
Shared-memory access and local sockets are same-host IPC, not network traffic.
Device-to-host staging is a separate host/device transfer.

Save performance belongs to `dcp-async-save-performance`; faster return or
higher write throughput does not establish recoverability.

## Establish four independent acceptance questions

| Question | Required evidence |
|---|---|
| Does the snapshot survive the declared failure? | Actual memory/storage/replica placement and helper lifetime |
| Is one generation complete across required participants? | Step/iteration identity, expected shard/rank set, successful finalization |
| Does that generation contain the application's complete state? | Model, optimizer and caller-required RNG/scheduler/data-position state contract |
| Can the target environment restore it? | Matching format, world-size/replication assumptions and separately authorized restore evidence |

Neither equal steps nor complete rank IDs verifies tensor contents or whole
application semantics. Record these as distinct evidence levels.

## C3 — DLRover memory, persistence and replicas

For queued save versus persistence/tracker completion, POSIX synchronization,
full/sharded Gloo replica transport and a bounded audit procedure, read the
[DLRover persistence and replica reference](references/dlrover-persistence-replicas.md).

The inspected save path filters to participating saving ranks, attempts the
shared-memory lock, and reduces readiness over the saver group. If not all
participants acquired access, it releases acquired locks and reports a skipped
save. Do not report that skipped generation as a new recovery point.

After memory write, it records the step and invokes replica backup. Recovery
first attempts replica-based memory restoration, reads checkpoint configuration,
then gathers steps over the loader group. It loads shared-memory state only
when those steps agree and the step is positive. A returned step paired with
an empty state dictionary is not proof of a successful restore.

| Failure domain | What this source establishes | What remains conditional |
|---|---|---|
| Training worker exits | Shared-memory recovery is designed to survive under an appropriate launcher/helper owner | The fallback daemon saver started outside `dlrover-run` exits with training and cannot persist afterward |
| One host loses local memory | Full/sharded managers exchange CPU bytes and metadata through Gloo | Actual surviving placement and restored payload values must cover the lost shard; inspected gather/consumer boundaries leave correctness unverified |
| All copies of a required shard are lost | Local shared memory cannot supply that shard | A separately valid persistent checkpoint is needed; not established by step agreement |

Code contains an HCCL-to-`npu` device branch. This is source availability, not
NPU runtime qualification. Replica transport is now source-inspected; the
engine's new-memory consumer allocates/sets metadata without a visible copy
from the received byte tensor. End-to-end restored-byte validity was not tested.
Do not upgrade allocation, metadata or a completed collective into proven recovery.

## C4 — NVIDIA Resiliency Extension complete iterations

`find_latest()` gathers locally available checkpoint IDs and selects the highest
iteration whose rank set exactly matches the participating group. With no
replication strategy, a rank considers only its own shards available. A local
maximum filename or one clean shard cannot substitute for global coverage.
`find_latest`, `save` and `load` require all training ranks to participate.

Local saves use an exclusive `.dirty` file, then rename it to the final name.
The finalizer recomputes global coverage; an incomplete requested iteration
causes cleanup of failed parts and an exception. Older checkpoints are cleaned
only on the successful branch. This is publication/completeness logic, not
power-loss durability: the inspected local writer does not establish fsync
semantics for the storage stack.

With `is_async=True`, this save path **synchronizes CUDA D2H before returning**
an `AsyncRequest`. The request must still be scheduled and finalized using the
matching queue contract. It is not an already-completed checkpoint and is not
equivalent to DCP's fully asynchronous staging. Do not assume unlimited queue
concurrency; the supplied guide's one-outstanding restriction remains the
conservative policy until the target queue version is checked.

Replication changes availability only if copies occupy independent failure
domains. Budget clean, dirty and replicated shards on each host. Keep session,
rank/world-size and replication parameters consistent: the inspected code has
a TODO around filtering changed replication parameters, not a guarantee of
elastic restore under arbitrary changes. The CUDA staging path does not
establish NPU compatibility.

## Proposed recovery evidence record

For each retained generation record: application step; expected participants;
actual shard IDs; primary/replica physical hosts; local publish status;
collective finalizer result; helper owner; selected fallback checkpoint; state
components and version/configuration. Include errors and skipped saves.

Future separately authorized verification should distinguish worker exit,
host loss, replica loss and persistent-storage loss, rather than testing one
and claiming all. This candidate neither injects failures nor authorizes them.
No recovery success, durability, NPU support or measured gain is claimed.
