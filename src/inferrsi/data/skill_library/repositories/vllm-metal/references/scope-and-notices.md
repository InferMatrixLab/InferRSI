# Extraction scope and notices

## Covered depth and remaining gaps

| Surface | Current scope |
| --- | --- |
| Platform/env/config/ABI | Selected substantive implementation, actual installed pure API inspection and parser/default tests; no native artifact build/load qualification |
| KV capacity, host/filesystem tiers, transfer and sleep/wake | Selected substantive owner/consumer/lifetime source and test assertions, offline dense-uniform arithmetic; actual storage/device/model operations not run |
| Speculation/deferred state/GQA/measurement | Selected pairing, FP32 recurrent-state guard, pending-token ownership, planner and source guidance; no native parity/dispatch/service measurement |
| Model matrix, format/loading, multimodal | Bounded route/guard evidence; no exhaustive supported-model matrix, tensor payload authentication, model conversion or image correctness |
| GGUF/AWQ/TurboQuant/MoE weight streaming | Mentioned boundaries and selected config facts only; deep packing/loader/kernels, numerical quality and real IO behavior unmined/unverified |
| DFlash/DSpark, diffusion, STT, embedding/pooling, LoRA | Named compatibility/route boundaries; detailed operating recipes and native model paths intentionally not extracted |
| Distributed PP/DP/Ray | Selected config/topology rejection boundaries only; no multi-host setup, transport/recovery mechanism qualification or Network coverage |
| Profiling/release/installer | Side effects identified; no host/toolchain/build/release execution, remote installer bundling or publication |

This is a partial repository operating graph with named long-tail gaps, not a
claim to reproduce every upstream public capability. Unknown future branches
must be researched, not inferred from generic vLLM/MLX knowledge.

## License boundaries

The retained [LICENSE](../LICENSE) is the upstream Apache-2.0 source license,
copied byte-for-byte from this source revision. Selected source/helper lineage
and attribution remain in the [readset](source-identity.json). New support code
is Apache-2.0; adaptations retain source attribution and SPDX headers. External
dependency and model/checkpoint/tokenizer/draft licenses are separate; no model
assets or upstream vendor source is copied into this graph.

Every root/sub-skill uses `license: NO_LICENSE` because the actual AREX GitHub
CLI resolver was unauthenticated and could not return a usable SPDX API value.
That fallback is a warning, not a legal conclusion that the repository lacks a
license, and does not replace the independently retained Apache-2.0 notice.
The runtime helper names are newly bundled support; they are not invented
upstream commands. Native source scripts requiring engines/datasets/services
remain provenance-only with distilled safe procedures, not runtime dependencies.

Prompt-derived KV state is sensitive even when named by hashes. New capture
must omit secrets and private paths, use synthetic/public records and preserve
failure/evidence limits. An example or source command grants no execution,
backup-exclusion, deletion, installation or service-launch authority.
