---
name: graph-and-compile
description: "Choose and debug TorchNPU manual NPUGraph, npugraphs, npugraph_ex, TorchAir, Inductor and FXRT compilation routes with explicit storage and backend gates."
---

# Choose capture and compilation paths

Use for graph replay, `torch.compile`, graph breaks, stale results, compiler
dependency failures or unexpected eager fallback. Read [the graph procedure](references/graphs.md)
and [failure recovery](references/troubleshooting.md).

Inputs: exact stack/revisions, backend name, eager function, input shapes/dtypes/
strides, mutation and aliasing, state/RNG, capture stream and output lifetime.
Output: selected backend contract, eager-versus-compiled/replayed comparison,
capture assumptions and unresolved compiler/device checks.

1. Establish a correct eager NPU result before capture.
2. Select manual NPUGraph, built-in graph backend, TorchAir, Inductor or FXRT
   explicitly; record optional compiler availability.
3. Preserve stable storage and legal stream/capture operations.
4. Compare updated-input replays, then benchmark after warmup and synchronization.
5. Use [the bundled graph case](../../scripts/runtime_smoke.py) with
   `--case graph --run` for a tiny manual replay check, not compiler conformance.

Use [memory](../memory-streams-and-events/SKILL.md) for pool/lifetime questions
and [operator development](../operator-development/SKILL.md) for missing Meta
or custom-op registrations. TorchAir and CANN internals remain external evidence
boundaries; no backend speedup is established by this source study.
