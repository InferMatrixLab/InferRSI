# Recovery reference evidence

Inspected 2026-10-15. Scope is recovery contracts, not performance or arbitrary
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
- C3 replica restoration invokes a manager and sets shared-memory metadata;
  its excerpt alone is insufficient to prove payload restoration. Keep that
  claim conditional pending implementation/restore evidence.
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
