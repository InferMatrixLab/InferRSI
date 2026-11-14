---
name: ascend-graph-mode
description: Diagnose an Ascend TorchAir ACL graph path from versioned configuration through FX compilation, capture-key selection, eager fallback, input staging, replay and output lifetime. Use when repeated inference has host overhead, capture churn, stale outputs or an uncertain backend; require source-matched configuration and separate device validation.
---

# Ascend Graph Mode: Configuration, Capture and Replay

Status: **candidate**; empirical validation: **not_run**. This owner combines a
historical imported skill with a bounded implementation read of official
`Ascend/torchair` at `e1118e8b0fc1b95190ab53b732c0872989550e20`.
The [source map](references/torchair-graph-path.md) and
[readset](references/torchair-graph-readset.json) distinguish inspected code,
documentation and test definitions. The read stops at TorchNPU/CANN calls;
it does not qualify their native implementation, a deployment stack or a speedup.
The historical `awesome-ascend-skills @ 75ec89ce` import and its UNKNOWN
license remain recorded in [legacy notes](references/legacy-source-notes.md).

## Establish the path before changing an option

Record hardware, driver/firmware, CANN, PyTorch, TorchNPU and TorchAir versions,
the backend actually passed to `torch.compile`, model/input shapes, dtype,
stride, mutation/aliasing and output retention. Confirm eager correctness first.
A source pin is an inspection identity, not a compatible installation recipe.

This skill follows TorchAir's Python `CompilerConfig` -> `_NpuFxCompiler` ->
`AclConcreteGraph` -> `AclGraph` path. The adjacent
[vLLM ACLGraph wrapper skill](../ascend-aclgraph-capture-replay/SKILL.md) owns a
different runtime dispatch and caller-buffer contract. A vLLM `--enforce-eager`
flag is not a generic TorchAir API. GE compilation, TorchNPU allocator internals
and native collective execution have separate owners.

Use graphs as a candidate when repeated work and measured host launch gaps
justify investigation. Include cold capture/compilation, warm replay, input
copies, output preservation, memory and concurrency costs. Shape churn,
kernel-bound work, repeated fallback or a tight memory budget are counter-signals.
Capture alone does not establish a kernel or service improvement; FX passes and
static compilation can separately change the executed work.

## Use the installed configuration surface

At the inspected pin, `get_npu_backend()` returns a **callable**, not a config.
`CompilerConfig.mode` owns the mode; `aclgraph_config` declares only
`use_custom_pool`. This source-derived example has not been run on an NPU:

```python
import torch
import torch_npu
import torchair
from torchair.configs.compiler_config import CompilerConfig

config = CompilerConfig()
config.mode = "npugraph_ex"
backend = torchair.get_npu_backend(compiler_config=config)
# model is the already validated NPU inference model.
compiled = torch.compile(model, backend=backend, fullgraph=True, dynamic=False)
# Run workload-specific comparisons under torch.inference_mode().
```

The same repository's quick start describes a registered `backend="npugraph_ex"`
supplied by the TorchNPU-facing interface, with `options={...}`. Do not combine
snippets from those surfaces or infer registration merely because TorchAir
imports successfully. Verify the installed backend and matching documentation.
`fullgraph=True` exposes graph breaks; `dynamic=False` is a bounded example,
not a requirement for every workload.

The exact fields below are declared in the inspected TorchAir code. Its optional
`options` mapping is implemented by `_process_kwargs_options`; some positive
option names invert the internal `disable_*` field.

| Intent | `CompilerConfig` field at this pin | Mapped option name |
|---|---|---|
| Run transformed FX without capture/replay | `debug.run_eagerly` | `force_eager` |
| Bound captured keys before fallback | `debug.aclgraph.static_capture_size_limit` | `capture_limit` |
| Stage ordinary inputs into captured storage | `debug.aclgraph.clone_input` | `clone_input` |
| Clone eligible outputs | `debug.aclgraph.enable_output_clone` | `clone_output` |
| Disable pool reuse among keys of one FX graph | `debug.aclgraph.disable_mempool_reuse_in_same_fx` | inverse of `reuse_graph_pool_in_same_fx` |
| Supply a graph pool | `aclgraph_config.use_custom_pool` | `use_graph_pool` |

`force_eager` is graph-wide here, not a per-operator escape hatch. Use a fresh
compiled instance and record effective configuration when changing options.
Do not invent fields such as `aclgraph_config.memory_reuse` or
`aclgraph_config.force_eager`. For fusion, static kernel compilation,
communication-in-graph or custom passes, inspect the installed option definition
and responsible implementation first; their bodies are outside this readset.

## Trace capture eligibility and fallback

1. Confirm the compiler selects `AclConcreteGraph`. At this pin,
   `max-autotune` selects `GeConcreteGraph`; `npugraph_ex` and deprecated
   `reduce-overhead` select ACL. Generated Python builds an `AclGraph`, loads
   capture metadata and calls it from `kernel`.
2. Identify symbolic/shape inputs in the key and whether parameter addresses
   are included. Frozen parameters omit their addresses and impose an
   address-stability contract. Equal shape does not prove reuse: changed
   mutated-input pointers or stream core limits can recapture an existing key.
3. Observe first capture, key reuse, recapture and fallback separately. On an
   uncaptured or recapture path, reaching `static_capture_size_limit` sets a
   persistent eager-fallback flag, synchronizes/resets captured graphs and
   routes subsequent calls to transformed FX eager execution. It does not
   merely skip one new shape; an already-reusable key returns before the limit
   check. Measure the shape/address distribution and resource cost before
   raising a cap.
4. Check logs/counters and a device trace. A mode string or one capture log is
   not evidence that later requests replayed or all intended work was captured.

## Preserve input and output ownership

Capture fixes addresses. The implementation treats ordinary inputs, mutated
inputs, parameters and input/output aliases differently. With input cloning,
ordinary NPU inputs receive captured storage and are copied before replay.
Without it, changed ordinary input addresses can still cause copies into
retained storage. Mutated-input address changes can cause recapture; aliases
have separate retained-pointer handling. Do not infer zero-copy from
`clone_input=False` or rely only on shape equality.

The replay wrapper calls `NPUGraph.replay()` first, then uses a separate
update-stream/task-update/event protocol when registered dynamic parameters
exist. Preserve that observed order. The TorchNPU event/task implementation
was not read, so this Python sequence does not prove native dependency semantics.

Returned outputs can reuse captured storage. Disabling pool reuse across keys
does not itself preserve old results across repeated execution of one key.
If a consumer needs an earlier result after another replay, explicitly preserve
it before that replay and verify alias/mutation behavior. `enable_output_clone`
clones eligible tensors but excludes storage identified as input/output aliases;
it does not copy every returned object. Custom pool selection also changes the
internal reuse policy at this pin. Concurrency and cross-graph pool sharing
require a separate lifetime/order investigation.

## Discriminate failures with one change at a time

| Observation | Candidate explanation | Next distinguishing check |
|---|---|---|
| First execution fails | Tracing, transformation, capture or stack mismatch | Compare ordinary eager, `aot_eager`, and `debug.run_eagerly`; retain exact errors. Eager success does not certify native graphs. |
| Same shape repeatedly captures | Mutated pointer, parameter key, core limit or separate FX graph changed | Record keys, relevant addresses and limits with capture counters. |
| Later calls lose replay | Capture limit caused persistent fallback | Revisit an earlier key after the limit event on the same instance; inspect trace/logs. |
| Retained results change after another request | Captured output storage was reused | Compare a preserved snapshot with the retained object after replay, including views/aliases. |
| Launch gaps shrink but latency does not | Device work, copies or scheduling dominates | Separate cold/warm phases and run the actual request mix with end-to-end timing. |

## Validation recipe and completion boundary

On a matching authorized NPU stack, freeze input/mutation/alias cases and
workload-specific numerical tolerances before comparing eager and compiled
execution. Exercise identical shapes with new data, changed addresses, multiple
keys, the configured capture limit, views/input-output aliases and retained old
outputs. Keep reference results outside reused graph storage. Check each
relevant branch, not just the first result.

Record capture/replay/fallback counts, correctness, memory/stream use, cold
cost, warm timing and representative concurrency. Separate optional fusion and
static compilation from capture-only changes. Multi-rank collective capture
also requires matching order, shape and completion checks on every rank; this
read provides no native collective certificate. Service claims require
service-level evidence.

The readset includes selected **stub-based ST definitions** for capture, reuse
and persistent fallback, and **NPU smoke-test definitions** for output cloning.
Neither suite was executed. Local source/hash/reader/package checks validate
the knowledge bundle only. Preserve unknowns when the required stack, workload
or native evidence is unavailable; do not promote the candidate or report a
performance PASS.
