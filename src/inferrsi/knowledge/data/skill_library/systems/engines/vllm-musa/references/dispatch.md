# The torchada dispatch boundary

Pinned to `vllm_musa/__init__.py` and `vllm_musa/platform.py` at the revision in
[sources.md](sources.md).

## What the plugin guarantees, and what it does not

- `vllm_musa/__init__.py` imports `torchada` before `torch` with an explicit
  comment: this must happen before any `torch.device("cuda:X")` call because it
  patches `torch.cuda` to redirect to MUSA.
- `musa_platform_plugin()` answers `vllm_musa.platform.MUSAPlatform` when
  `torchada.is_musa_platform()` is true, and otherwise falls back to importing
  `torch_musa`. Availability of the compat layer is part of runtime identity.
- The import block is wrapped in `try/except ImportError` and only sets
  `_torchada_available`, so an environment can reach the fallback path silently.

What this does **not** guarantee: that any given CUDA-shaped kernel, fused op,
graph pass or attention backend exists, is selected, or is fast. A source-level
fast path can compile and run through the compatibility layer while the work is
done by a different implementation.

## Porting checklist for one CUDA optimization

1. **Name the mechanism.** "Fewer kernels", "one fewer round trip", "smaller
   activation" — one sentence, tied to a named kernel or graph node.
2. **Prove the mechanism exists on MUSA.** Search the plugin and the built
   wheel for the symbol; a CUDA-only distribution that the MUSA image excludes
   cannot be the mechanism (see [omni.md](omni.md) for the constraint list).
3. **Prove it is selected.** Profile one steady-state step and look for the
   kernel names. Generic or fallback names mean the fast path did not win.
4. **Then measure** with the pair rules in [measurement.md](measurement.md).
5. **Record the compat layer.** `torchada`, `torch_musa`, `torch` and the MUSA
   toolkit versions go next to the number; a different `torchada` revision is a
   different runtime.

## False positives to expect

- The candidate "improves" because it changed warmup length, batch shape or
  graph capture state rather than the kernel.
- The candidate is inert on MUSA (guarded by a CUDA-only check) and the delta is
  run-to-run noise.
- Both arms execute the fallback, so the comparison is really fallback versus
  fallback with different bookkeeping.

Each of these is decided by a profile plus an identical-pair rerun, not by the
engine-level number alone.
