# Cross-cutting troubleshooting

| Symptom | Check | Recovery |
|---|---|---|
| `pip install .` fails or starts unexpected setup | This repo's setup script is an application bootstrapper | Use the explicit build or prepared application environment; inspect dependencies before invoking setup |
| Option is ignored or cannot be parsed | Installer, server and engine expose different option surfaces; model family matters | Inspect the appropriate parser and actual engine command; preserve startup fallback messages |
| OOM after a setting change | KV, MTP, batch state, graph captures and prefill workspace share the expert-cache budget | Restore baseline, identify the allocation, then change one memory component |
| Low-RAM mode is extremely slow | File-mapped experts may fault from SSD; RAM residency and pinning may have failed | Check resident/mapped mode and page faults; reduce working set or use an allowed larger memory budget |
| Same seed produces different text | CPU/GPU rounding, draft grouping, adaptive residency, prompt reuse and approximate defaults | Stabilize these paths for diagnosis; use logits/task quality as well as text equality |
| Faster benchmark but worse user latency | Queuing, prompt length, cache state, concurrency or token-count source differs | Re-run matched cold/warm workloads; report client TTFT and request tails |
| CPU tests pass but GPU backend unavailable | Native kernels/model execution remain unverified | Record `BLOCKED_REQUIRED_BACKEND`; hand off exact build/parity/serving checks |
| Stale tokens after cancel or wrong restored conversation | In-flight windows, cache ownership or rollback state may be corrupted | Reject the candidate, preserve the failing case, restore the baseline |
| Trial summary rejects input | Missing IDs, mixed comparison conditions, duplicate trial IDs or non-finite metrics | Repair data provenance; never delete failed measurements merely to improve rank |

Use the detailed [validation cookbook](../sub-skills/validate-engine/references/validation.md) for commands and backend prerequisites.
