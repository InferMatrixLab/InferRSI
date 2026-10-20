---
name: ascend-graph-mode
description: 'How to configure, debug, and optimize Ascend NPU graph mode (npugraph_ex / aclgraph): capture-and-replay mechanics, FX pass configuration, memory reuse, static kernel compilation, communication-in-graph, forced-eager fallback, and the document-first lookup discipline for CANN configuration options. Source-grounded from awesome-ascend-skills torch-npugraph-ex-knowledge skill.

  '
---

# Ascend Graph Mode (npugraph_ex / ACLGraph)

Status: candidate. Source-grounded from awesome-ascend-skills @ 75ec89ce,
`external/cannbot/graph/torch-npugraph-ex-knowledge/SKILL.md`. License UNKNOWN
(synced from GitCode). Verify against your CANN/TorchAir version.

## What it is and when to use it

npugraph_ex mode uses Capture & Replay to lower host scheduling overhead by
sinking operator tasks to the device. It is an experimental feature for
inference only — not for training. It is beneficial for:
- Fixed-shape online inference where the same kernel sequence repeats.
- Scenarios where host overhead is the measured bottleneck (confirmed via
  profiler — see `ascend-performance-analysis` skill).

Do not enable it as a default without measuring that host overhead is actually
the bottleneck. Graph capture adds startup cost and constrains shape flexibility.

## Configuration API

The canonical configuration surface is `config.aclgraph_config`.

```python
import torchair  # TorchAir
from torchair._core.backend import npugraph_ex_config

config = torchair.get_npu_backend()
config.mode = "npugraph_ex"   # not "reduce-overhead" — that is deprecated
```

Rule: do not set options beyond what is needed. Only set the specific option
the user requested; leave everything else at its default.
Source: torch-npugraph-ex-knowledge SKILL.md § 核心规则.

## Document-first discipline

For any `aclgraph_config` option, **look up the TorchAir documentation before
writing code**. Do not rely on memory for parameter names, defaults, or behavior.
The relevant docs are in `Ascend/torchair` at `docs/zh/npugraph_ex/`.

Primary doc map (paths relative to torchair repo `docs/zh/`):

| Feature | Path |
|---------|------|
| Mode overview | `npugraph_ex/npugraph_ex.md` |
| Quick start | `npugraph_ex/quick_start.md` |
| FX fusion pass | `npugraph_ex/basic/pattern_fusion_pass.md` |
| In-place pass | `npugraph_ex/basic/inplace_pass.md` |
| Memory reuse between graphs | `npugraph_ex/basic/memory_reuse.md` |
| Static kernel compilation | `npugraph_ex/basic/static_kernel_compile.md` |
| Frozen parameter (fixed weights) | `npugraph_ex/basic/frozen_parameter.md` |
| Capture limit | `npugraph_ex/basic/capture_limit.md` |
| Communication in graph | `npugraph_ex/basic/communication_graph.md` |
| Force eager fallback | `npugraph_ex/basic/force_eager.md` |

Fetch via sparse checkout:
```bash
git clone --depth 1 --filter=blob:none --sparse \
  https://gitcode.com/Ascend/torchair.git ~/.cache/torchair-docs
git -C ~/.cache/torchair-docs sparse-checkout set docs/zh
```
Source: torch-npugraph-ex-knowledge SKILL.md § 文档获取方式.

## Key features and their configuration

**FX fusion passes:** FX graph passes fuse operator patterns at capture time.
Configure via `config.aclgraph_config.pattern_fusion_pass`. Check
`pattern_fusion_pass.md` for supported patterns before expecting a fusion to
occur — not all pattern types are covered.

**Memory reuse:** `config.aclgraph_config.memory_reuse` controls whether
intermediate buffers are reused across successive graph replays. This reduces
peak HBM usage but requires that the graph's output does not alias a fused
intermediate. Verify correctness after enabling.

**Static kernel compilation:** `config.aclgraph_config.static_kernel_compile`
compiles kernels statically at capture time rather than JIT-compiling on first
replay. Improves steady-state latency; adds startup cost. Use for production
serving workloads where startup time is not a bottleneck.

**Communication in graph:** collective operations (AllReduce, AllGather) can
be captured into the graph. Enable via `communication_graph.md` guidelines.
Increases capture complexity and startup time; verify that the collective
participates in every graph replay with identical sizes.

## Fallback and debugging

**Force eager fallback:** if specific ops fail during graph capture, use
`config.aclgraph_config.force_eager` to run those ops outside the graph. This
is a debugging and compatibility tool, not a production optimization. Document
which ops fell back and why; file a support issue for ops that should be in-graph
but are not.

**Capture limit:** `config.aclgraph_config.capture_limit` limits how many times
a graph shape can be recaptured. Unlimited recapture on dynamic shapes can cause
unbounded startup latency and memory use.

**Diagnosis approach for graph-mode failures:**
1. Run with `--enforce-eager` to confirm the model works outside graph mode.
2. Enable graph mode and check whether `Replaying aclgraph` appears in logs.
3. If capture fails, check for unsupported ops — look for `force_eager` messages
   or `not supported in graph mode` errors in the startup log.
4. If replay fails with shape errors, check whether the serving code is passing
   variable-shape inputs to a graph captured for a fixed shape.

## Performance expectations

Graph mode reduces per-step host scheduling overhead, which matters most when:
- The model is compute-light (small batch, few layers) so host time is visible.
- The request throughput is high (host overhead becomes a bottleneck under load).

Graph mode does NOT reduce kernel execution time or AI Core utilization. If the
bottleneck is inside the kernel (memory-bound or compute-bound), graph mode
provides little benefit. Confirm the bottleneck class with `profiling-analyze`
before attributing latency to host overhead.
