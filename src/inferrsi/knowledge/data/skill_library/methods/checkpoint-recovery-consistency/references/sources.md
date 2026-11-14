# Recovery reference evidence

Original inspection: 2026-10-15. Scope is recovery contracts, not performance or arbitrary
checkpoint-system investigation. Sources are independent implementations;
NVIDIA local checkpointing includes Megatron-Core lineage and is not counted
again as a separately mined Megatron mechanism.

| Entry | Immutable readset | Evidence strength and license |
|---|---|---|
| C3 DLRover | [engine.py readiness/step/backend, 60–116](https://github.com/intelligent-machine-learning/dlrover/blob/e35b1ad90e2928ca6bacf5d22117f713566c5cb0/dlrover/trainer/torch/flash_checkpoint/engine.py#L60-L116); launcher 139–158; [memory save/load/replica, 365–440](https://github.com/intelligent-machine-learning/dlrover/blob/e35b1ad90e2928ca6bacf5d22117f713566c5cb0/dlrover/trainer/torch/flash_checkpoint/engine.py#L365-L440) | Code and embedded docs directly read. Root LICENSE retrieved (Apache-2.0 plus retained notices). Replica transport/saver implementation and successful recovery not established by this excerpt. |
| C4 NVIDIA Resiliency Extension | [base_manager.py, 157–234](https://github.com/NVIDIA/nvidia-resiliency-ext/blob/49af0b03f14550d36a60dcfebd573848b5fd8435/src/nvidia_resiliency_ext/checkpointing/local/ckpt_managers/base_manager.py#L157-L234); [save/finalize, 237–317](https://github.com/NVIDIA/nvidia-resiliency-ext/blob/49af0b03f14550d36a60dcfebd573848b5fd8435/src/nvidia_resiliency_ext/checkpointing/local/ckpt_managers/base_manager.py#L237-L317); [local_manager.py, 78–154](https://github.com/NVIDIA/nvidia-resiliency-ext/blob/49af0b03f14550d36a60dcfebd573848b5fd8435/src/nvidia_resiliency_ext/checkpointing/local/ckpt_managers/local_manager.py#L78-L154) | Code directly read; source headers explicitly Apache-2.0, copyright NVIDIA. Root `LICENSE` URL returned 404; that does not negate scoped SPDX evidence or establish licenses for other files. |

## Carried versus newly inspected evidence

Dot B's C3 recovery design and C4 usage-guide notes are supplied documentation
context. The one-outstanding async-queue restriction and Basic state dictionary's
CUDA assumption are carried guide evidence, not newly audited queue/base-state
implementations. Directly read C4 `save` itself calls `torch.cuda.synchronize()`
before returning an asynchronous request. C3 exposes an HCCL device branch,
without a tested torch_npu/GLM integration.

## Boundaries that affect decisions

- C3 saver/loader groups are actual contract participants; "all ranks" must
  not silently mean every world rank regardless of its saving role.
- The original C3 excerpt did not audit the saver/replica implementation. The
  extension below supplies that source trace; restored-byte validity remains
  unverified, with concrete gather/consumer boundaries retained.
- C4 `find_latest` caches its result until a save invalidates it, explicitly
  assuming no other invalidation. It is not a continuously refreshed durability
  monitor. `load` requires a prior `find_latest`.
- C4 available-ID coverage is not a content checksum, corruption check or
  optimizer/RNG/data-position completeness check. Local `torch.load` uses
  `weights_only=False`; artifacts must come from a trusted checkpoint source.
- C4 async queue internals, replication transfer algorithm and base state-dict
  implementation were not read. No independent failure test was performed.

All derived failure-domain and verification requirements are candidate guidance.
No source throughput numbers, runtime results or empirical PASS are imported.

## DLRover extension: inspected 2026-10-22

All new source reads use `intelligent-machine-learning/dlrover` at full revision
`e35b1ad90e2928ca6bacf5d22117f713566c5cb0`, fetched as immutable UTF-8 files
through the GitHub connector. The following ranges were directly read; method
names and file paths describe evidence, not instructions to execute upstream
scripts. The [operating reference](dlrover-persistence-replicas.md) distills the
behavior and proposed checks. Existing C4 evidence was not refreshed.

| File / inspected lines | Directly observed scope |
|---|---|
| [`ddp.py`, 15–125](https://github.com/intelligent-machine-learning/dlrover/blob/e35b1ad90e2928ca6bacf5d22117f713566c5cb0/dlrover/trainer/torch/flash_checkpoint/ddp.py#L15-L125) | Public wrapper, state/path mapping, saver construction, discarded save return and wait delegation |
| [`full_ckpt_engine.py`, 15–220](https://github.com/intelligent-machine-learning/dlrover/blob/e35b1ad90e2928ca6bacf5d22117f713566c5cb0/dlrover/trainer/torch/flash_checkpoint/full_ckpt_engine.py#L103-L220) | Cached-step branch, save event/barrier/return, memory-first load and explicit-path versus tracker-selected storage fallback |
| [`engine.py`, 60–116, 139–158, 214–310, 365–469](https://github.com/intelligent-machine-learning/dlrover/blob/e35b1ad90e2928ca6bacf5d22117f713566c5cb0/dlrover/trainer/torch/flash_checkpoint/engine.py#L365-L469) | Existing readiness/step/backend and helper-lifetime contracts; manager selection, shared-memory save/backup, gather consumer and timeout return |
| [`ckpt_saver.py`, 98–112, 176–231, 303–396, 419–466](https://github.com/intelligent-machine-learning/dlrover/blob/e35b1ad90e2928ca6bacf5d22117f713566c5cb0/dlrover/python/elastic_agent/torch/ckpt_saver.py#L303-L396) | Shared-memory create/copy and writing flag; load rejection; saver storage construction, handler/lock/executor ownership |
| [`ckpt_saver.py`, 619–746, 770–852, 892–1122, 1341–1345](https://github.com/intelligent-machine-learning/dlrover/blob/e35b1ad90e2928ca6bacf5d22117f713566c5cb0/dlrover/python/elastic_agent/torch/ckpt_saver.py#L962-L1122) | Event consumer, shard lock/step/write/done ordering and exception result; interrupted-worker save gates; common-directory count/timeout/tracker protocol and serialization map; DDP saver inheritance |
| [`replica.py`, 31–363](https://github.com/intelligent-machine-learning/dlrover/blob/e35b1ad90e2928ca6bacf5d22117f713566c5cb0/dlrover/trainer/torch/flash_checkpoint/replica.py#L31-L363) | Full/sharded selection; CPU/Gloo groups, topology world positions, byte/metadata gather and peer-memory writes; full presence/broadcast and shard-owner lookup |
| [`storage.py`, 24–62, 89–192, 264–320](https://github.com/intelligent-machine-learning/dlrover/blob/e35b1ad90e2928ca6bacf5d22117f713566c5cb0/dlrover/python/common/storage.py#L128-L192) | Storage boundary, POSIX write/fsync and callback-owned payload serialization, read/move/list/commit; optional deletion callback |
| [`LICENSE`, complete file](https://github.com/intelligent-machine-learning/dlrover/blob/e35b1ad90e2928ca6bacf5d22117f713566c5cb0/LICENSE) and inspected Python file headers, 1–12 | Root applies Apache-2.0 unless otherwise noted; scoped files retain DLRover Authors' Apache-2.0 headers. Root also retains third-party notices; no implementation text is copied into this extension |

### Observation versus proposed evidence

The saver compares done-file count, not an authenticated rank/content manifest.
`PosixDiskStorage.write` contains `fsync` before context close and no explicit
buffer flush before that call; payload serialization is delegated. These facts
do not prove power-loss durability or a reproduced durability failure.

Sharded gather keys handlers by global rank but initially indexes by loop
position (`replica.py`, 224–255). The engine's missing-local-memory branch
allocates and sets metadata without visibly copying the returned bytes
(`engine.py`, 423–440). These are source observations motivating specific
topology and restored-value checks, not executed failure reports.

Excluded: TempDir commit implementation, framework-specific serializers beyond
the DDP/common saver, third-party serializer internals, custom storage, device
execution, distributed collectives, failure injection, power-loss tests and
agent-use evaluation. No new runtime qualification or measured coverage follows
from this readset.
