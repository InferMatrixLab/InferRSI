---
name: pytorch-sdpa-backend-selection
description: "Select PyTorch scaled-dot-product attention backends and flash-impl activation from the v2.15 context manager. Use for backend flags and priority, not for a measured attention speedup."
---

# PyTorch SDPA backend selection

Status: candidate. Empirical validation: **not_run**. Pin: `31a77fc9c0a7c6fff15a1ff58c743f53b1a9d457`.

## Procedure

1. F: `torch.nn.attention.sdpa_kernel` enables a subset of `MATH`, `FLASH_ATTENTION`, `EFFICIENT_ATTENTION`, `CUDNN_ATTENTION` and `OVERRIDEABLE`, then restores the previous flags on exit. The docstring also says exit enables all backends. The implementation restores `previous_backends`. P: trust the restore, and record the flags you observed rather than the exit sentence.
2. F: `set_priority=True` writes the user order and then appends any previously ordered backends that were missing. Priority is not a guarantee that a backend can run.
3. F: `WARN_FOR_UNFUSED_KERNELS` defaults to false. When true, the helper warns only through `can_use_efficient_attention` and `can_use_flash_attention`. It does not explain a cuDNN rejection.
4. F: `register_flash_attention_impl` stores a callable. `activate_flash_attention_impl` first restores any previous override, then calls that callable. Providers are told not to activate on import. `restore_flash_attention_impl` removes a handle when one exists; its docstring says it restores the default FA2 implementation. P: a successful activate is an opt-in registration, not a benchmark.
5. F: `sdp_utils.h` declares `select_sdp_backend` and the `can_use_*` predicates. The function bodies are not in that header. P: do not invent the winner for a shape, dtype or mask.

## Later check

Under an authorized run, log `torch.nn.attention._cur_sdpa_kernel_backends(with_priority=True)` around one forward, then compare numerics before timing. This skill has no such log.

## Limits

FlexAttention and fused kernel sources were not read. CUDA-graph capture of SDPA stays with the existing compiler card. NPU attention is not this skill.
