# Cache and offload troubleshooting

Use the [ownership contract](cache-and-offload.md) to distinguish source policy
from observed runtime behavior. These are diagnostic branches, not permission
to start a service, alter the OS, delete private KV files or change user data.

| Signal | Likely boundary | Small discriminating check / recovery |
| --- | --- | --- |
| Bigger host pool reduces token capacity | Automatic KV sizing subtracts host bytes from the same unified-memory budget | Compare startup `kv_offload_pool` and `kv_budget`; use the bundled dense ledger only when its assumptions hold; do not sum independent RAM and VRAM allowances |
| Explicit KV bytes appear to leave the pool uncounted | Explicit cache budget covers cache alone | Count host pool/weights/workspace additionally; pressure probe still applies; raising utilization does not increase explicit bytes |
| One chunk or one request does not fit | Chunk alignment floor plus rounded request and null block | Confirm actual block/chunk alignment; distinguish request-alone shortage from offload-caused shortage; a user-set pool is not automatically capped |
| Planner shrinks after startup probe | Actual compression/swap displacement, not merely low idle free bytes | Preserve probe output and future reserves; free competing memory or reduce required footprint before retry; do not blindly increase utilization |
| Probe command fails or times out | Required macOS pressure counters unavailable | Report unavailable; opt-out is an explicit removal of the safety check, not a successful probe; do not silently set it to zero |
| Connector/group/executor rejected | Native-only, one full-attention group, `uni`, no incompatible state/draft cache | Correct the unsupported combination or remove offload in an authorized configuration; no generic fallback promises |
| Host view mismatch or carve error | Disk tier and worker would observe different bytes/layout | Stop; compare real pointers, page order, aligned chunk geometry and matched runtime version; do not silence the check |
| Loaded prefix is overwritten or absent | Indexed MLX assignment misses backing storage, or pending zeroing precedes restore incorrectly | Require native scatter into the real storage allocation plus evaluated cache pages and a consuming operation; CPU list copies cannot validate this |
| Duplicate destination or bounds error | Native scatter could race/corrupt cache | Validate IDs, group count, mid-chunk offset and enough host chunks; repair the producer, not the guard |
| Sleep succeeds but pages remain | Page release is best-effort, and peak RSS is historical | Inspect release warning and current residency separately; retained weights/other allocations do not imply failed KV release |
| Wake page reuse fails | OS has not reclaimed previously reusable pages for writes | Stop wake; do not continue writing or suppress the failure; require actual backend recovery evidence |
| Disk prefixes missing after restart | xxhash seed changed, namespace/dtype/layout changed or files evicted | Prefer stable hashes for qualified restart reuse, reconcile namespace and cap; a configured seed is not proof of checkpoint identity |
| Replaced checkpoint reuses old cache | Store key does not hash actual weights | Plan a separate namespace or authorized scoped cleanup; do not automatically delete a supplied directory |
| Disk store remains above cap | In-flight files pinned, failed deletions or another process shares the root | Inspect job/completion/accounting records; per-process cap is not a shared global quota; isolate roots in an authorized deployment |
| Directory permission warning | Existing owned root is group/world accessible | Report risk; source warns rather than silently changing existing ownership/modes; obtain authority before chmod/cleanup |
| `.noindex` mistaken for privacy/backup exclusion | Spotlight avoidance is not encryption or Time Machine policy | Keep derived KV private, check authorized backup policy; don't publish filenames/content or assume hashes anonymize prompts |

Native transfer, sleep/wake and restart correctness require compatible macOS,
MLX, matched vLLM/plugin/native artifact and actual device execution. Missing
backend evidence remains **BLOCKED_REQUIRED_BACKEND** even when byte arithmetic
and parser fixtures pass. Model-quality and E2E performance require separately
qualified workloads; route them to [qualification](../../qualification/SKILL.md).
