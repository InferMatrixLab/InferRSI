---
name: cache-lifecycle
description: "Diagnose vllm-metal paged KV capacity, offload host and filesystem
  tiers, transfer ordering, reuse identity and sleep/wake ownership without
  mistaking a byte ledger for native memory-fit evidence."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
---

# Cache capacity, residency and lifetime

Use this source-derived **candidate** when a Metal run exhausts cache, restores
the wrong prefix, fails offload startup, retains memory while idle or reports
capacity that does not match resident memory. Read the
[ownership and sizing contract](references/cache-and-offload.md) before changing
flags. Required real Apple MLX/Metal execution remains
**BLOCKED_REQUIRED_BACKEND** unless separately established; offline arithmetic
does not qualify native transfers, model outputs, memory pressure or speed.

## Choose the narrow investigation

| Symptom or question | First action |
| --- | --- |
| More host offload appears to create extra RAM | Separate automatic versus explicit-cache budgets; count one physical pool |
| A model/connector/executor combination fails before serving | Apply the eligibility table, not a bigger pool |
| Restore is invisible or overwritten after a transfer | Inspect storage ownership, native scatter and completion ordering |
| Old prefixes survive a restart or a checkpoint replacement | Inspect hash seed, dtype/model identity and store namespace |
| Sleep says success but memory remains or wake fails | Distinguish best-effort page release from required page reuse |
| Disk cache grows, contains private prompt state or shows stale hits | Inspect per-process cap, in-flight pins, permissions and backup policy |

## Procedure

1. Record the exact plugin/vLLM/MLX build, model and actual checkpoint identity,
   attention/cache group types, dtype/layout, block size, context, parallelism,
   executor, speculative method and all cache/offload settings. A model name is
   not a digest of its weights. Keep prompt-derived KV files private.
2. Identify the owner and phase. vLLM owns scheduler blocks; the Metal runtime
   owns the storage view and transfer worker; the offload manager owns host/disk
   indices. Capacity planning is not allocation, and allocation is not resident
   commitment. Host and accelerator views share physical unified memory.
3. Check offload eligibility before sizing. A single uniform full-attention
   group is required; MLA, sliding/grouped/hybrid, draft-model groups, pooling,
   STT, PP/DP and non-`uni` executors do not acquire support from a successful
   pure-Python config check. See the exact split guards in the reference.
4. Distinguish budget modes. An automatic KV budget subtracts weights,
   execution overhead and future workspaces before the host pool; an explicit
   `kv_cache_memory_bytes` budgets cache alone, with the host pool additional.
   A user-set host pool is not silently reduced like an automatic pool.
5. For dense uniform arithmetic only, use
   [screen_pool_budget.py](scripts/screen_pool_budget.py) and its
   [input/output contract](references/helper-contract.md). It runs with Python
   standard library, reads at most 1 MiB and performs no native imports,
   allocation probe, service launch or file mutation:

   ```bash
   python scripts/screen_pool_budget.py --example
   python scripts/screen_pool_budget.py --example | python scripts/screen_pool_budget.py -
   ```

   Run from this sub-skill directory or resolve both script paths from its
   installed resource. Exit zero means only a conflict-free declared ledger.
6. Read startup profiling and the real commit-probe result separately. Missing
   or failing pressure counters are not zero pressure. Disabling the probe
   changes the safety check, not the machine's available memory. Do not fix a
   paging cap by blindly increasing `gpu_memory_utilization`.
7. For transfer correctness, require the same real storage allocation before
   and after restore, actual cache-page bytes, correct IDs/offsets, pending-write
   ordering and a subsequent native consumer. An MLX indexed assignment to a
   page view is not a substitute for the worker's native scatter.
8. For sleep/restart/reuse, reconcile index lifetime, bytes and source identity.
   Empty in-memory prefix/host indices after wake do not imply the disk store is
   empty. Do not erase a user store, change its permissions or exclude backups
   without explicit authority; prepare a scoped plan and stop for permission.
9. Verify only the claimed scope. A helper fixture can check arithmetic; native
   worker roundtrips can check selected byte transfer behavior; model parity and
   complete serving load/quality need their own frozen protocols. Route a
   benchmark or speculative-state claim to
   [qualification](../qualification/SKILL.md).

## Stop and report

Use [troubleshooting](references/troubleshooting.md) for the discriminating
check and safest recovery. Report declared identities, actual owner/lifetime,
evidence class, conflicting setting or invariant, proposed bounded action and
the missing native check. Keep unavailable backend/model results unverified or
INCONCLUSIVE; successful config parsing or green scaffold CI is never a serving
or native-cache PASS. The helper intentionally rejects grouped/compressed
layouts and does not authenticate that a declared model is uniform.
