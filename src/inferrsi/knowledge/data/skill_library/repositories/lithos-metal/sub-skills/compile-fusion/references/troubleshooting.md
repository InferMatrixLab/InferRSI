# Compilation and fusion failures

| Symptom | Inspect | Next bounded action |
| --- | --- | --- |
| `CoverageError` lists ops with no kernel | Profile key, op registry and actual graph | Supply a supported binding or supported model path; never defer the missing op to runtime. |
| `fusion regions must be disjoint...` | Emitted span endpoints and unique labels after prior transformations | Reconstruct boundaries from current kernel roles; do not reuse stale indices. |
| Unsupported tile/operand/worker geometry | Format/layout, active row bound, normalization mode and chip recipe | Retain native/normalized control. A recipe copied from another chip is unqualified. |
| Fused wrong, normalized correct | Written bindings, StepState predicates, local versus cross-worker publication, task bounds | Reduce to one region with the same numerical control. Preserve a bounded failure; do not lengthen spin loops blindly. |
| `Megakernel: bounded worker barrier timed out` / state error 3 | Stage participation, uniform barriers, task queue bounds and device/recipe match | Stop the affected experiment; compare safe native path and capture minimal diagnostic state. `barriers='all'` does not fix intrakernel deadlock. |
| Incorrect only after scratch reuse | Known producers, first reads, preserved outputs/state, offsets and renamed hazards | Retain original buffers and compare. Reapply barrier placement after any physical alias change. |
| Dispatch count drops but round slows | Original vs normalized vs fused cost, sync, spills/storage and entire region | Keep all observations; reject a speedup inference from dispatch count alone. |
| Numerical drift after normalization | `commute_norm`, decoded format, fast math, reference rounding/reduction order | Match numerical settings before attributing a fusion defect; qualify intentional changed rounding independently. |

A workaround is a candidate change until checked against actual selected rows,
state and backend. Source tests and isolated timings cannot establish service
quality or performance.
