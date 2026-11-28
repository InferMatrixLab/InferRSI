# Runtime-memory troubleshooting

Use symptoms to choose a small discriminating observation, not to infer a
universal optimal configuration. All native experiments require separate
authorization, compatible hardware and matching model files.

| Symptom | Possible cause and concrete next check | Recovery or stop |
| --- | --- | --- |
| A `32GB` cache request does not match the startup cache | The request is an expert-cache target; slot quantization, prefill headroom, mandatory model/graph/context allocations and backend guards constrain the effective result | Record both values and startup's breakdown. Reduce context/slots or cache only after identifying the pressured component; do not disable guards |
| `--ssd-streaming-cache-experts 32` seems unexpectedly small | A bare decimal means 32 slots, not GiB | Use an explicit integer `GB` suffix for a byte target, then inspect the effective allocation. Reject `32G`, `1.5GB`, zero and negative values rather than silently guessing intent |
| Larger expert cache slows generation after prefill | Non-routed weights may no longer remain resident; OS pressure or staging competes with the cache | Keep prompt/context/slots fixed, compare memory pressure and reads in append/decode, and reduce the routed cache. A changed cold/warm state invalidates the comparison |
| One session fits but four do not | Per-slot KV/recurrent state and planned mandatory graph allocation remain even where prefill scratch is shared | Budget planned plus active slots and the actual context limit. Reduce slots or context; never extrapolate from model-file size alone |
| Additional slot looks almost free in tensor counters | It may borrow prefill scratch or pooled views; this does not prove no private state or host allocation exists | Inspect the full phase/owner ledger and physical process memory, then test independent-session state. Retain uncertainty if allocator/OS accounting is unavailable |
| Shared workspace reports incompatible capacity or embedding tier | Borrowed arena is smaller than the requested prefill capacity or belongs to a different embedding tier | Rebuild/reallocate through the owning engine path with compatible capacity/tier; do not alias the pointers manually or free a borrower's arena |
| CUDA `...=0` does not turn off a diagnostic switch | The relevant SSD switches test environment-variable presence | Unset the switch. Record all related enable/disable switches; explicit disable takes precedence |
| CUDA prefill comparison changes but decode does not | Selected-read ordering is enabled by default for the batched prefill path, not ordinary single-token reads | Measure prefill and decode separately. Treat whole-next-layer prefetch as a separate policy with its own prerequisites |
| CUDA placement refuses despite enough summed VRAM | Whole-layer placement and replicated/shared/graph/context allocations must fit individual devices | Check the selected per-device budgets, ordering and active mode. Choose a supported smaller model or reduce state; no unsupported CPU spill assumption |
| A model loads metadata but cannot execute or stream | Unsupported tensor layout/model/backend pairing; DwarfStar is not a generic GGUF runtime | Stop before allocating/downloading more. Reconfirm the exact project-compatible checkpoint and backend; a matching bit width is insufficient |

## Measurement hygiene

Keep cold load, initial prefill, continuation prefill, first-token delay and
steady decode separate. Record preloaded experts, cache occupancy, context,
concurrency, sampling and optional draft/vision paths. A short generation can
expose an unusable interactive configuration but does not qualify long contexts,
quality or service behavior. Successful CPU bookkeeping or source inspection
does not resolve `BLOCKED_REQUIRED_BACKEND` for actual accelerator memory,
storage overlap, model quality or throughput.

## Script decisions

Model download scripts are excluded: they perform large network/storage changes
and require checkpoint-license and capacity decisions. The upstream NVIDIA TP
launcher is reference-only because it embeds deployment-specific paths and
policy; use the placement invariants in the bundled memory ledger, not a copied
launcher. Benchmark/conversion tooling is outside this route's bounded scope.
No small independent runtime-memory script was copied: the safe offline request
builder is owned at the root, while memory-fit arithmetic without the full
backend/model allocator would risk presenting an estimate as an allocation
guarantee.
