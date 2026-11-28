# Launch and communication contracts

## Small reproducible collective

Use two or more accessible NPUs with matching installed packages and CANN/HCCL.
Each worker selects its `LOCAL_RANK` device before `init_process_group("hccl")`.
Use an explicit finite timeout and a rendezvous endpoint provided at runtime;
never bake a real host address into a reusable skill. For a single node:

```bash
torchrun --standalone --nproc-per-node=2 <SKILL_ROOT>/scripts/runtime_smoke.py --case hccl --run
```

The helper requires valid launch rank variables, checks device availability,
all-reduces a tiny rank-dependent tensor, waits on the returned work, synchronizes
and verifies the expected sum. It destroys its process group on exit. It does
not validate cross-node networking, topology, huge messages or training overlap.
Ensure all ranks run the same case. Do not launch it on a shared allocation
without access to all selected devices.

## Registration and stream mechanism

The Python registry registers `hccl` before `lccl` for NPU devices, uses the
extended backend API and transfers group rank/size/store, timeout and group
identity into ProcessGroupHCCL options. LCCL is a separate backend; registering
it does not establish equivalent HCCL capabilities (F15).

C++ collective execution obtains the group's communicator/communication streams
and records a producer-stream event that blocks each HCCL stream. That dependency
alone does not protect storage lifetime: the allocator records the communication
stream, or a configured mode stashes tensor references. Certain unknown/P2P
paths deliberately fall back to record-stream protection. Outputs can need
their own protection in the operation-specific path (F16).

The work future is marked completed in the collective launch path before its
device end-events are recorded. Do not equate this host-side future state with
completed network/device transfer. `WorkHCCL::wait` delegates to synchronization
that blocks the current consumer stream on the HCCL end-event, and only loops
on the host in configured blocking-wait mode; barriers have an explicit device
synchronization branch. For host-read/timing validation, synchronize the relevant
device/stream after waiting (F17).

## Hangs and timeout analysis

Find the first diverging collective across ranks before changing timeouts.
Record rank, sequence, operation, dtype/numel and group membership for each
participant. First compare collective order and rank/device mapping, then
rendezvous and communicator creation, then producer stream readiness, dispatch
and execution. Distinguish process-group watchdog timeout, HCCL execution/event
timeout and launch/rendezvous timeout. Changing all timeouts simultaneously
conceals which stage failed. Blocking-wait and asynchronous error-handling
configuration alter monitoring behavior; preserve exact settings when reducing
a reproduction. Never disable watchdog/error handling as a generic fix.

## Higher-level boundaries

FSDP, DTensor rules, distributed functional collectives, pipeline patches,
RPC/Tensorpipe, symmetric memory and distributed Muon are inventoried in the
[support reference](../../../references/support-workflows.md). These layer on
different sharding/autograd/topology/transport contracts. For a sharded workload,
retain placement/local-shape/global-shape and group identities and verify
collective correctness first. RPC requires the separately pinned Tensorpipe
dependency; symmetric memory requires its external SHMEM runtime. Their mere
source presence is not full operating support or runtime validation.
