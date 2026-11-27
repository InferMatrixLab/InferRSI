# Ranks, collectives, sharded state and serialization

## Distributed job contract

Inputs: launcher/rendezvous, rank topology, device/backend per process, model
and data partition, collective sequence, timeout and trusted network/storage.
Output: consistent rank/device map, completion/correctness checks and a restart
or restore procedure. Missing ranks or hardware remain explicit blockers.

1. Establish single-process eager correctness. Pick backend by the installed
   build and device: commonly CPU/Gloo or CUDA/NCCL, XPU/XCCL where supported.
   Check availability; a Windows CPU/Gloo run does not qualify Linux NCCL.
2. Use `torchrun`/`python -m torch.distributed.run` and consume LOCAL_RANK,
   RANK and WORLD_SIZE. For one process per GPU set its device before model
   allocation and init_process_group. Rank is global identity; LOCAL_RANK
   is the node-local device selector, not an interchangeable world rank.
3. Specify backend and initialization policy. `env://` uses launcher rendezvous
   variables; store and init_method are mutually exclusive. Keep job endpoints
   on a trusted isolated network. Never expose TCPStore/RPC to untrusted peers.
4. All members must call collectives with compatible order, group, shapes,
   dtypes/devices and semantics. Create overlapping groups in a globally
   consistent order. Retain the first rank exception before interpreting a
   later timeout as a network failure.
5. Async collectives return Work handles. Keep inputs/outputs alive until their
   operations finish and establish stream ordering before subsequent use.
   NCCL Work.wait synchronizes the current CUDA stream with the NCCL stream;
   ordinary wait is not necessarily a host/device-wide fence. Host blocking
   depends on blocking-wait/timeout/barrier behavior. An unrelated consumer
   stream still needs its dependency. No CPU timing claim follows from enqueue.
6. Destroy process groups coherently after outstanding work completes. A
   timeout/abort is not permission to continue using potentially corrupted
   asynchronous device state; restart through the job's failure policy.

The bundled [rank diagnostic](../scripts/rank_contract.py) is a tiny public-API
all-reduce plus DDP backward/update. Run, for example, in a trusted local job:

```bash
python -m torch.distributed.run --standalone --nnodes=1 --nproc-per-node=2 <SUBSKILL_DIR>/scripts/rank_contract.py --backend gloo --device cpu
```

It uses launcher-provided endpoints and a finite group timeout; it is never
started merely by loading the skill. Select `--backend nccl --device cuda`
only with two assigned devices and a supported stack. Multi-node membership,
fabric and failure recovery need separate tests.

## DDP, FSDP2 and DTensor

DDP replicates model state and synchronizes gradients through reducer hooks.
Hooks mark parameter gradients ready; buckets are reduced in a consistent
order across ranks rather than arbitrary ready order. Configure unused-parameter
handling only when graph structure needs it. DDP does not shard input data for
you. Use DistributedSampler or explicit data partitioning. Gradient accumulation
with no_sync needs the forward and backward inside the intended context and
one correctly scaled final synchronization. For compilation, the pinned guide
wraps in DDP before torch.compile so bucket-aware graph partitioning can apply.

FSDP2 `fully_shard` changes model parameters to DTensor in place; hooks unshard
before computation and reshard/free full parameters afterwards. Apply it
bottom-up to intended layers, then root, to define communication groups.
Construct the optimizer **after** sharding from the resulting parameters.
Call `model(x)` so hooks fire; bypassing hooks with `.forward()` needs explicit
supported unsharding/registration. More wrapping is not universally better:
measure all-gather/reduce-scatter overlap, peak residency and actual step time.
FSDP1 legacy flattening/wrapping is a distinct API and checkpoint format contract.

DTensor represents global layout using DeviceMesh plus per-mesh-dimension
Shard/Replicate/Partial placements. `from_local` assumes the caller's local
shards really implement the declared global tensor; `to_local` is not an
implicit gather. `redistribute`/`full_tensor` can communicate and increase
memory. Record global versus local shape and placement before combining with
tensor parallel, pipelining or FSDP. Pipeline schedules, RPC/distributed autograd,
symmetric memory and elastic recovery have backend/version-specific contracts;
preserve explicit stage/order/lifetime checks rather than assuming DDP proves them.

## Trusted torch.save state workflow

1. Use state_dict with registered parameters and persistent buffers. Save
   optimizer/scheduler/scaler, RNG and progress when exact training resume is
   required. A state_dict weights file is not an executable module definition.
2. Load only an artifact of established provenance. Prefer explicit
   `torch.load(path, map_location="cpu", weights_only=True)`, then validate
   expected keys, tensor shapes/dtypes/numel/resource bounds and call
   `load_state_dict` with appropriate strictness before device transfer.
3. weights_only restricts unpickling to allowed tensor/primitive/global types;
   it is not a general hostile-input sanitizer or a denial-of-service defense.
   Do not switch to weights_only=False or add safe globals merely to suppress
   an error; establish trust in the file and each allowlisted class first.
4. `mmap=True` lazily maps compatible file storage; it does not stream arbitrary
   checkpoints into bounded GPU memory or make unpickling safe. Use an actual
   compatible path/ZIP-format artifact and preserve the file lifetime.
5. torch.save preserves storage/view relationships. A tiny slice can serialize
   its entire base storage. Clone before saving only if breaking aliases is
   intended. Verify aliases as well as values after loading when they matter.
6. Recreate model and optimizer according to their registration/group contracts,
   load state and run a tiny forward/backward/update comparison. Weight equality
   alone is weaker than resume equivalence.

## Distributed checkpoint workflow and trust boundary

DCP saves sharded multi-rank state and supports load-time resharding. It writes
multiple files and loads into allocated target storage; initialize the model
and desired sharding topology before load. All participating ranks must agree
on state keys and call sequence. Use the public state_dict helpers appropriate
to the installed FSDP/DTensor stack; validate a new-topology resume explicitly.

DCP and its format conversion tools assume **trusted job-produced storage**.
They do **not inherit torch.load weights_only protections**. For example,
BroadcastingTorchSaveReader explicitly uses weights_only=False on its coordinator
load. Do not feed downloaded/untrusted artifacts to DCP conversion, metadata
inspection or load. Network primitives also lack an untrusted-peer authorization
boundary; this route does not authorize a public rendezvous service.

For async save, distinguish completion of staging from durable checkpoint
completion and hold required state/buffers until the appropriate future finishes.
Bound in-flight saves; copying/staging can consume host/pinned memory even while
device computation continues. The existing DCP async-save owner retains detailed
staging/performance guidance and its own pin; this route supplies correctness,
trust and ownership inputs rather than duplicating that evidence.

Run [state roundtrip](../scripts/state_roundtrip.py) for a tiny self-created
weights-only/mmap diagnostic. It never opens caller-supplied checkpoint files.
It does not qualify DCP, sharding, asynchronous durability or artifact safety.


Source support at the pinned revision (exact inspected spans and byte digests are in the root [readset](../../../references/source-readset.json)):

- [`torch/distributed/distributed_c10d.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/distributed/distributed_c10d.py)
- [`torch/csrc/distributed/c10d/ProcessGroup.hpp`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/csrc/distributed/c10d/ProcessGroup.hpp)
- [`torch/csrc/distributed/c10d/ProcessGroupNCCL.cpp`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/csrc/distributed/c10d/ProcessGroupNCCL.cpp)
- [`docs/source/notes/ddp.md`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/docs/source/notes/ddp.md)
- [`docs/source/distributed/fsdp.fully_shard.md`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/docs/source/distributed/fsdp.fully_shard.md)
- [`docs/source/distributed/tensor.md`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/docs/source/distributed/tensor.md)
- [`torch/serialization.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/serialization.py)
- [`torch/distributed/checkpoint/format_utils.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/distributed/checkpoint/format_utils.py)
- [`SECURITY.md`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/SECURITY.md)
- [`docs/source/notes/serialization.md`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/docs/source/notes/serialization.md)
- [`docs/source/distributed/checkpoint.md`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/docs/source/distributed/checkpoint.md)
- [`torch/distributed/checkpoint/state_dict_saver.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/distributed/checkpoint/state_dict_saver.py)
