# Flare source map

Task identity: [NVIDIA/flare-local-inference](https://github.com/NVIDIA/flare-local-inference).
On 2026-10-28 it redirected to [NVIDIA/local-inference](https://github.com/NVIDIA/local-inference).
This delivery retains **bce032c014bae34502ba22d3304fa084d5b40afe** throughout;
the redirect is not an upgrade. [Machine-readable ledger](source-ledger.json)
records the canonical pinned tree, selected file Git blobs, byte counts and
SHA-256 identities. All selected raw bytes matched that tree. Only the named
sections/symbols below were inspected; whole-file identity is not whole-file
coverage.

F means a source-level mechanism/contract; DOC means upstream design intent;
TEST-SOURCE means an inspected assertion without execution. P in the procedures
means a proposed diagnostic action. None is a native/agent-efficacy result.

## Preparation readset

| Key | File / inspected scope | What it establishes |
|---|---|---|
| F1 / CODE | [`helios/src/execution/manifest.rs`](https://github.com/NVIDIA/local-inference/blob/bce032c014bae34502ba22d3304fa084d5b40afe/helios/src/execution/manifest.rs#L5): `ABI_VERSION`, `ExecutionManifest::validate`; [`runtime_package/format.rs`](https://github.com/NVIDIA/local-inference/blob/bce032c014bae34502ba22d3304fa084d5b40afe/helios/src/runtime_package/format.rs#L265): `Package::validate` ABI/storage checks | Execution ABI 4; incompatible execution contracts fail before graph replay |
| F1 / CODE | [`helios/src/model/contract.rs`](https://github.com/NVIDIA/local-inference/blob/bce032c014bae34502ba22d3304fa084d5b40afe/helios/src/model/contract.rs#L340): `PreparedContract::validate`; [`runtime_package/model.rs`](https://github.com/NVIDIA/local-inference/blob/bce032c014bae34502ba22d3304fa084d5b40afe/helios/src/runtime_package/model.rs#L438): typed prepared-contract decode and embedding-table bound checks; `model/catalog.rs::validate`, called by `server/runtime.rs` before executor construction | Prepared contract 2; typed semantic validation is distinct from package format |
| F1 / DOC | [`README.md`](https://github.com/NVIDIA/local-inference/blob/bce032c014bae34502ba22d3304fa084d5b40afe/README.md), [`docs/runtime-package-design.md`](https://github.com/NVIDIA/local-inference/blob/bce032c014bae34502ba22d3304fa084d5b40afe/docs/runtime-package-design.md) §§1–2 | Research-prototype SM120/SM121 scope; preparation/export/native ownership; nonportable live handles; independent payload/carrier versions |

The generic addition belongs to the
[weight-loading preparation reference](../../../../methods/weight-loading-optimization/references/flare-preparation-boundary.md).
Exporter code, native package reconstruction, signing/security qualification,
model recipes and CUDA kernels were not audited.

## Session, admission and observation readset

| Key | File / inspected scope | What it establishes |
|---|---|---|
| F2 / CODE | [`helios/src/cache.rs`](https://github.com/NVIDIA/local-inference/blob/bce032c014bae34502ba22d3304fa084d5b40afe/helios/src/cache.rs#L239): publication structs/ownership contract, `publish`, `lookup`, `mark_used`, `retire_leaf`, `compact_ancestor`, `cancel_publication`, `advance_completed` | Complete endpoint/page/snapshot identity; publish/use/retire fences and delayed ID reuse |
| F3 / CODE | [`offload/mod.rs`](https://github.com/NVIDIA/local-inference/blob/bce032c014bae34502ba22d3304fa084d5b40afe/helios/src/offload/mod.rs#L724): `HostHit`, `InboundTicket`, `StoreEvent`, `LookupOutcome`, `PrefixStore`, `worth_fetching`; explicit Direct rejection | Five outcomes; additional-token conditional cost policy; enqueue/completion/drain contracts; GDS not implemented |
| F3 / CODE | [`offload/geometry.rs`](https://github.com/NVIDIA/local-inference/blob/bce032c014bae34502ba22d3304fa084d5b40afe/helios/src/offload/geometry.rs#L39): `CacheGeometry`, `Layout`, `fingerprint`; [`offload/index.rs`](https://github.com/NVIDIA/local-inference/blob/bce032c014bae34502ba22d3304fa084d5b40afe/helios/src/offload/index.rs#L216): `lookup_below`, `chain`; [`offload/record.rs`](https://github.com/NVIDIA/local-inference/blob/bce032c014bae34502ba22d3304fa084d5b40afe/helios/src/offload/record.rs#L707): header decode/validation, directory identity, `scan` | Pages plus complete row geometry; rowless intermediate versus resumable endpoint; namespace/layout/ancestor scan checks |
| F4 / CODE | [`helios/src/scheduler.rs`](https://github.com/NVIDIA/local-inference/blob/bce032c014bae34502ba22d3304fa084d5b40afe/helios/src/scheduler.rs#L1373): `plan_admission`, `admit_planned`, `finish_inbound`, `fail_ticket`, `take_publications`, `cancel`, `finish`, `retire`, `release_after_shutdown` | Scheduler-owned shared tickets; waiter cancellation; completion/publication and drain-gated release |
| F5 / CODE | [`server/runtime.rs`](https://github.com/NVIDIA/local-inference/blob/bce032c014bae34502ba22d3304fa084d5b40afe/helios/src/server/runtime.rs#L2081): `admit_with_host_store`, publication/store-event polling, shutdown handling; [`offload/transfer.rs`](https://github.com/NVIDIA/local-inference/blob/bce032c014bae34502ba22d3304fa084d5b40afe/helios/src/offload/transfer.rs#L485): `submit`, `poll`, `close`, rank-reply bookkeeping | Actual five-branch consumer; new/shared ticket distinction; completed fetch/requeue; accounting all rank replies and retaining unconfirmed work |
| F2–F5 / DOC | [`docs/prefix-cache-offload.md`](https://github.com/NVIDIA/local-inference/blob/bce032c014bae34502ba22d3304fa084d5b40afe/docs/prefix-cache-offload.md) §§1, 2.1–2.2, 2.5–2.10, 4–6 | Complete continuation types, namespace/configuration intent, GDS explicitly deferred, planned validation and known limitations; implementation-sequence/proposed thresholds are not completed measurements |
| F6 / TEST-SOURCE | [`tests/server/test_prefix_cache_offload.py`](https://github.com/NVIDIA/local-inference/blob/bce032c014bae34502ba22d3304fa084d5b40afe/tests/server/test_prefix_cache_offload.py#L114): disabled-offload, restart/ordinary-speculative separation, corruption, checkpoint-pressure tests and server fixture | Required model/GPU/package-backed assertions; no test in this file was run |
| F7 / CODE | [`qualify/performance.py`](https://github.com/NVIDIA/local-inference/blob/bce032c014bae34502ba22d3304fa084d5b40afe/qualify/performance.py#L350): `analyze_events`, `stream_request`, `group_summary`, measurement definitions and measured-group checks; [`qualify/provenance.py`](https://github.com/NVIDIA/local-inference/blob/bce032c014bae34502ba22d3304fa084d5b40afe/qualify/provenance.py): `digest`, `file_record`, `checkout_record` | Coalesced token groups; client/native clock separation; actual reused-token/resource checks; exact file identity versus execution evidence |

## Attribution and exclusions

The selected source is Apache-2.0; the exact upstream root
[LICENSE](../LICENSE) is retained. No model weights/assets or vendored/dependency
code were copied. Their separate licenses and model access rights are outside
that repository-root notice and remain independently applicable.

The preparation and Flare session owners share this evidence through links;
there is one full session ledger, not a second catalog/database. The existing
vLLM and LMCache owners remain engine-specific. The source includes multi-rank
paths and validation plans, but this slice does not qualify their hardware,
multi-host transport or failure behavior. Kernel algorithms, model integration,
upstream installation, benchmarks and the separate InferRSI offline adapter are
outside this source-distillation delivery.
