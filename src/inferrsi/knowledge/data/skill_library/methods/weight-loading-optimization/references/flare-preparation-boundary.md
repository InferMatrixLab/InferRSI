# Flare preparation and native-serving boundary

Source-derived candidate; empirical validation **not_run**. This adds one
preparation-contract example to the existing loading owner, not another generic
loading skill. The [pinned source map](../../../repositories/flare-local-inference/audit-flare-session-lifecycle/references/source-notes.md#preparation-readset)
defines the immutable files and symbols. No Flare installation or preparation
was performed.

## Responsibility and lifetime

| Owner | During preparation | What reaches serving |
|---|---|---|
| Ignition (Python) | Model recipes, checkpoint acquisition, load/tune/compile/capture; declares allocations/cache, tensor views, semantic contracts, graph handles and resource owners | Export declarations and data supplied to heliopause; its live Python owners stay on the preparation side |
| heliopause (Rust CPython extension) | Preparation allocator, graph introspection, pointer reachability, payload transfers, graph/package serialization and publication; retains resources through native export work | Serialized graphs/storage/contracts and packaged assets, rather than live Python/graph handles |
| Helios (Rust library) | No Python preparation ownership | Loads/validates the package, rebuilds storage and CUDA graphs in a live context, and owns native scheduling/cache execution |
| flare (Rust executable) | Public deployment build/CLI | Links Helios and serves the prepared package; no embedded Python interpreter |

The dependency direction is `flare → Helios` and `heliopause → Helios`.
The design says graph templates, storage, CUDA contexts and Python resource
owners are retained until native export work drains; failed drain retains them.
`ignition export` writes the package, closes the prepared model and exits;
`flare run` loads the result in a separate process. CUDA graph handles and
Python resource owners do **not** cross that boundary. These exporter lifetime
details are DOC evidence; the exporter implementation itself is outside the
selected readset.

The saved package describes storage/graphs/contracts so the serving process can
reconstruct them. Recorded addresses and relocation metadata are package data;
they do not make a process-local CUDA handle or Python object portable. The
prepared model also declares disposable KV/scratch state separately from
initialized weights and required metadata. Do not infer that exporting every
live preparation allocation is necessary or that a smaller payload proves
lower peak preparation memory.

## Verify independent version domains

| Domain | Pinned rule | Concrete source |
|---|---|---|
| Execution ABI | Version 4; another value is rejected and requests re-export | `execution/manifest.rs::ABI_VERSION`, `ExecutionManifest::validate`, `runtime_package/format.rs::Package::validate` |
| Prepared model contract | Version 2; typed vocabulary/geometry, vision/frontend and graph semantics must validate | `model/contract.rs::PreparedContract::validate` |
| Payload/carrier format | Documentation describes payload format 2 and signed format-6 logical-resource containers; neither number is an execution/prepared-contract version | `docs/runtime-package-design.md`, carrier implementation not qualified here |
| External embedding resources | Every referenced graph embedding-table index must exist in the loaded table catalog | `runtime_package/model.rs` typed-contract decode and table-bound check |

P: For a load rejection, first record exporter/source pin, package digest,
runtime pin, all three domains and the actual error. If ABI or prepared
contract differs, re-export through the matching preparation path when
authorized. Rewriting a version tag does not convert graph parameters,
storage geometry or semantic bindings. A successful format parse is not
semantic validation, and semantic validation is not model-output validation.

## Account preparation separately

P: Keep checkpoint acquisition, compilation/tuning, graph capture/export,
serving package read/reconstruction, readiness warmup and request execution as
separate phases. Compare equivalent package/model/configuration and cold/warm
conditions before attributing a startup change. "No Python in serving" describes
the process boundary; it alone supplies no performance-causation evidence.

For request-time prefix reuse, continue with the
[Flare session owner](../../../repositories/flare-local-inference/audit-flare-session-lifecycle/SKILL.md).
Its KV chain must accompany recurrent/convolution/partial-tail continuation
state. A prepared package is different from a per-session persisted checkpoint.

## Applicability and licenses

The source is a research prototype targeting NVIDIA SM120/SM121 and selected
models/local workloads. No cross-backend, broad multi-card or device execution
qualification follows from these contracts. Its GDS transport remains deferred;
preparation serialization is unrelated to a claim of direct-storage execution.

The selected repository files are under the root Apache-2.0
[license retained by the Flare owner](../../../repositories/flare-local-inference/audit-flare-session-lifecycle/LICENSE).
This notice covers source attribution, not a grant over model weights,
tokenizer/assets or separate dependencies. Their own licenses and access
conditions remain separate; none was imported or independently cleared here.
