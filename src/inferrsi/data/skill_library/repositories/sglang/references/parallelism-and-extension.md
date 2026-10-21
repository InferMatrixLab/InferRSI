# Parallelism and implementation boundaries

Read for topology changes, disaggregation, model integration, attention backend or kernel work. Pair this reference with [validation](tuning-and-validation.md).

## Topology is a contract

| Dimension | Meaning at this snapshot | Required observations |
|---|---|---|
| TP | Model tensor partitioning (`--tp-size`) | Weight/head divisibility, per-rank memory and collective cost |
| Replica DP | Independent model replicas (`--dp-size`) | Routing balance, each replica's capacity, total hardware |
| Attention DP | Attention groups inside a TP group, one scheduler each; FFN remains TP (`--attn-dp-size`) | Group participation, uneven prefill/decode, padding/communication |
| EP | Expert distribution (`--ep-size`) and selected MoE all-to-all/runner backend | Expert load skew, tokens per expert, dispatch/combine correctness, network |
| PD | Separate prefill/decode roles (`--disaggregation-mode`) plus a transfer backend | Bootstrap identity, matching layouts, KV allocation/transfer, timeout and failure lifecycle |

The TP/DP declarations distinguish replica DP and attention DP. Old `--dp-size N --enable-dp-attention` maps to attention DP and resets replica DP; prefer the explicit current spelling and inspect local compatibility hooks. EP is not a substitute for attention TP. There is no universal multiplication formula for every hybrid topology: validate the actual model and group construction. [E14](source-map.md#e14), [E15](source-map.md#e15), [E16](source-map.md#e16), [E38](source-map.md#e38)

PD can isolate prefill work from decode but adds transfer/routing cost and resource fragmentation. Compare a colocated baseline at the same total hardware budget. In the current `prefill_complete` decode-allocation policy, both roles must agree; reservation waits until prefill completes, and the implementation has explicit backend/layout/feature restrictions. It can hold KV longer on prefill and remove transfer overlap. Read the policy validator before selecting it; do not copy it as a general speed flag. [E17](source-map.md#e17)

Before distributed launch, draw process/rank ownership and state the model/tokenizer revision, dtype/KV layout, page size and transport on both peers. Test uneven loads, idle ranks, finish/abort, and transfer failure. A timeout is evidence to diagnose, not a reason to increase every timeout.

## Configuration changes

This revision preserves raw `ServerArgs` input and projects resolved configuration into namespace bags through `publish`. Runtime decisions use the relevant accessor (`get_schedule`, `get_memory`, `get_exec`, etc.); the named override path records effective changes. Per-runner differences belong to the owning runner/constructor and must not leak into a process-wide bag. Read the full native `sglang-runtime-context` skill before touching these boundaries. [E21](source-map.md#e21)

An existing knob changes a supported setting. A new configuration field or policy branch is an implementation change requiring declaration, resolution, consumer, documentation and test updates. A new optimizer, transfer protocol or scheduling algorithm is a research extension until its invariants and evaluation are established.

## Models and attention backends

The model registry scans model modules' `EntryClass`, supports explicit external registration, and reports import/architecture failures. Start from a semantically close model, then verify config/architecture identity, RoPE/position and attention semantics, weight names and TP sharding, logits, quantization, and any multimodal token expansion. Do not silently overwrite an existing architecture registration. The guide's “one model file” is an entry point, not evidence that all architectures need only one changed file. [E18](source-map.md#e18), [E37](source-map.md#e37)

Attention implementations are selected through registered factories. Trace the selected backend's actual planning and forward paths for prefill, decode, verify, graph replay and the relevant KV layout. Check dtype, head dimensions, masks/window, tensor strides, positional encodings, and cache-write semantics against a reference path. A registry entry alone does not make a backend valid for every model. [E19](source-map.md#e19), [E05](source-map.md#e05)

## Kernels

Public in-tree callable kernels live under `sglang.kernels.ops.<group>`; shared JIT infrastructure lives in `sglang.kernels.jit`, while the AOT wheel retains its own API. The old `sglang.jit_kernel` path was removed. Group by computation; retain model-specific tuning data inside the relevant group. Process groups, communication buffer ownership and model dispatch remain in `srt`. [E20](source-map.md#e20)

Use lazy `KernelSpec` metadata or the existing `BaseFusedOp` contract as appropriate. Describe supported device/architecture and input contract; a backend inventory is not a benchmark-based best-choice ranking. Keep a numerical reference and test shapes, dtypes, strides, edge sizes, aliasing and capture/replay. For a move, update runtime imports, lazy targets, tuning paths, tests and CI registrations together. [E20](source-map.md#e20), [E22](source-map.md#e22)

Tests belong to `test/registered/kernels/ops/<group>/`, microbenchmarks to `test/registered/kernels/benchmark/<group>/`, and CPU inventory checks to `test/registered/unit/kernels/`. Runtime integration tests stay with their subsystem, even when they allocate on GPU. Register the actual test entry point and preserve exit codes so CI can fail. [E23](source-map.md#e23)

## Acceptance by change class

| Change | Minimum evidence before acceptance |
|---|---|
| Existing topology/config | Parser and compatibility validation; resolved settings; intended hardware run; output parity and SLO comparison |
| Model/backend/kernel implementation | Targeted numerical/logit tests; cache/graph modes; sharding and weight-load checks; end-to-end model quality and workload benchmark |
| Research extension | Explicit invariant/algorithm argument; baseline and ablations; failure cases; finite experiment budget; correctness and performance on the claimed domain |

If a required domain cannot be tested, narrow the claim to the checked domain and state the remaining gate. Do not generalize a single-device microbenchmark to production serving.
