# DLRover persistence and replica boundaries

Scope: DLRover FlashCheckpoint at the revision in the
[source inventory](sources.md#dlrover-extension-inspected-2026-10-22).
The persistence trace covers DDP's `FullCheckpointEngine` with
`DdpCheckpointSaver` / `CommonDirCheckpointSaver` and POSIX storage. It does not
establish TempDir, FSDP, DeepSpeed, Megatron, custom-storage or device behavior.
Replica branches are source-inspected; restore correctness remains unverified.

## Follow the owner of each completion signal

| Boundary / owner | Directly observed behavior | What the signal does not establish |
|---|---|---|
| DDP public wrapper | Wraps caller state as `model_states`, builds the path map, delegates memory/disk save, and discards the engine return value | A normal public call does not expose even the engine's Boolean acceptance result |
| Full checkpoint engine | If needed, attempts memory save; after a distributed barrier, successful local rank zero queues `SAVE(step)` and updates `latest_step` | The Boolean return and barrier do not wait for storage writes or tracker publication |
| Shared-memory handler | Publishes `writing_shm=True`, copies state, then republishes `False`; load returns empty for missing metadata, a writing flag or missing memory | A step in metadata alone does not establish readable payload or application-state completeness |
| Async saver | Consumes `SAVE`, checks cached steps, starts local shard futures, and waits for their Boolean results | This is separate from the training caller's completion; local success is not global commit |
| Shard task | Acquires its memory lock, rechecks event step, invokes persistence, then writes a rank-named done file; exception returns `False` and releases the lock | A marker says the persistence callback returned, not that all required state was serialized |
| Rank-zero common-directory committer | Polls `len(listdir(done_dir)) == global_shard_num`, updates tracker, removes done directory and calls `storage.commit(step, success)`; timeout removes done directory without advancing tracker | It checks a count, not the expected rank-ID set, contents, checksums or semantic state completeness |
| Wait helper | Polls the tracker through local `open`; timeout logs and breaks; no success value is returned | Return is not a success receipt; this helper also does not establish a custom storage backend's read contract |

The saver persists directly to configured paths, rather than publishing a new
generation with the NVIDIA `.dirty`-to-final protocol. Do not transfer that
other implementation's publication guarantee to this path. The generic
persistence method skips missing configuration/paths, and writes only truthy
state entries whose names occur in the path map. A done file does not verify
that the map included optimizer, RNG, scheduler or data-position state.

### Storage ordering is a separate question

`PosixDiskStorage.write` calls `stream.write(content)` and then
`os.fsync(stream.fileno())` inside a Python file context, with no explicit
`stream.flush()` before `fsync`. Closing the context happens afterward.
`write_state_dict` delegates to its supplied serializer; the inspected wrapper
adds no explicit payload-file or directory synchronization. `commit` only logs.

These are source observations, not a power-loss experiment or a claim that all
serializer/filesystem combinations fail. Do not interpret the presence of
`fsync` on marker/tracker writes as proof that buffered marker bytes, payloads,
directory entries and the complete generation are durably ordered. Establish
the actual serializer, storage/filesystem contract and failure test before
making that stronger claim. A custom storage implementation needs its own audit.

## Replica transport and its consumer

The engine selects the full manager when global shard count is one, otherwise
the sharded manager. `has_replica()` tests configuration (`replica_count > 0`),
not surviving payload availability. Both managers use CPU tensors and explicit
Gloo groups when distributed replication is enabled; the engine's separate
HCCL readiness branch does not qualify this transport on NPU.

| Branch | Source-observed transport and placement | Recovery boundary |
|---|---|---|
| Sharded | Computes groups from rendezvous world position and local rank. Here `replica_count` sets group width, including the owner; do not read it as that many additional remote copies. Gathers byte sizes, pads to the maximum, all-gathers bytes and metadata, then copies peers into rank-keyed shared memory before setting metadata | Check actual global ranks, physical hosts, group bounds and payload sizes. Gather attempts to find an owner's nonempty replica metadata; it does not independently checksum bytes or prove matching application state |
| Full | Selects local rank zero from each node; backup is a no-op because full snapshots already exist per node. Gather exchanges memory-presence flags, chooses the first available source, broadcasts padded bytes and metadata | Presence selects a source; it does not select the newest complete generation or validate its contents. No replica when all flags are zero. Nonparticipants return no payload |

Two concrete source observations prevent accepting restored-byte correctness
from this trace alone:

- Sharded gather builds its handler dictionary using global rank keys, while
  `_gather_owner_checkpoint` first looks up `shm_handlers[i]` using the loop
  position. For a group such as `[1, 3]`, the key set and lookup differ. Check
  this exact topology on the target revision before accepting that restore path;
  no distributed failure has been reproduced here.
- After `gather` returns bytes and metadata to an engine with no local memory,
  `_restore_memory_from_replica` allocates shared memory and sets metadata,
  but contains no copy from the returned byte tensor into that new buffer.
  Allocation, metadata, its log message and the final barrier are insufficient
  evidence of payload restoration. Verify reconstructed tensor values through
  the consumer, including the new-buffer path.

Retain the original loader gate: equal, positive steps across the loader group
are required before shared-memory load, and the handler can still return empty.
This agreement does not repair missing bytes or prove complete training state.

## Bounded operating procedure

1. **Fix the path and failure domain.** Record version, wrapper/engine/saver,
   storage implementation, serializer, save paths, expected shard/rank set,
   physical primary/replica hosts and helper owner. Distinguish worker exit,
   host-memory loss, loss of every replica and persistent-storage loss.
2. **Check admission before naming a new recovery point.** Preserve the saver
   group's lock/readiness result and skipped saves. A queued step, public
   return or `latest_step` is not a persisted-generation receipt.
3. **Check persistence evidence at the actual owner.** Correlate event step,
   shard-write outcomes, expected payloads, done-file names and tracker step.
   Preserve timeout/write errors and the last independently verified fallback.
   Use payload/state validation in addition to the implementation's count gate.
4. **Check replica coverage through the consumer.** Select full versus sharded
   manager, map group ranks to hosts, and inspect actual surviving bytes and
   generation metadata. Treat the two source observations above as specific
   target-version checks, rather than assuming successful collectives restore data.
5. **Separate publication from durability.** Confirm serialization and storage
   synchronization ordering, atomicity and failure behavior for the declared
   storage. Reading a tracker or listing files is not a power-loss test.
6. **Request only the missing evidence.** Under separate authorization, compare
   known tensor/state values after a real restore, including missing-local-memory
   and nonzero/noncontiguous rank-group cases; test worker, host and storage
   failures separately. Keep readiness/step disagreement regression coverage.
   Stop at source-derived uncertainty if those resources are unavailable.

No distributed/backend execution, recovery, durability, throughput or agent
efficacy result is established by this procedure. Retain the fallback daemon's
parent lifetime limit and the independent NVIDIA finalization contract in the
owning skill.
