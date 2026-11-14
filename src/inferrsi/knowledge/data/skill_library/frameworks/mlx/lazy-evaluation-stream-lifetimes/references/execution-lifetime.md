# Evaluation, ordering and ownership

Read IDs in [source-map.md](source-map.md) as source observations, not measured results.

| Stage | Owner and lifetime | Consequence |
|---|---|---|
| Operation construction | Array descriptor holds primitive and input graph (F1) | Python operation submission need not perform the full calculation. |
| Graph scheduling | eval_impl discovers dependencies, builds its tape and routes the primitive (F2/F3) | Preserve producer/consumer stream identities; a default-device label is insufficient. |
| Cross-stream ordering | Per-evaluation fences; unfinished events from earlier async work (F3) | A dependency wait is needed even when consumer execution is asynchronous. |
| In-flight execution | Metal completion-handler captures, CPU dispatched captures, CUDA encoder temporaries (F4) | Detaching the graph must not end the buffers' required lifetime. The mechanisms differ by backend. |
| Read availability | Array event wait changes availability (F2) | Marked evaluated is not equivalent to host-readable completion. |
| Failure | eval_impl attempts to flush/signals/waits and rethrows (F5) | Keep the original error; test whether subsequent independent work is usable. |

Concrete path: `add` creates `Add(to_stream(s))` with promoted/broadcast inputs → Python `eval` flattens arrays → C++ `eval` → `eval_impl` → fence/event waits → CPU/GPU primitive → backend completion retention → synchronizer/array wait. `async_eval` submits the graph without the final host wait used by `eval`.

The graph has a tracer distinction: async evaluation of an unscheduled tracer is rejected; non-tracer evaluated arrays can detach primitive/input references. Do not recommend moving evaluation blindly into `grad`, `vmap` or compile contexts (F2/F3, T1).

For memory investigations, first determine whether the retained object is a graph edge, an in-flight buffer or allocator cache. The inspected lifetime path establishes retention obligations, not the allocator's eviction policy or a universal leak threshold. A unified-memory statement does not remove synchronization, cache-coherency or bandwidth costs.
