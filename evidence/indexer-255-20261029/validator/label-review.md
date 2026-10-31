# Independent source-label audit (before retrieval scoring)

These qualifications do not modify frozen inputs, numerical gates, candidate code or raw scores.

1. **dev02 is ambiguous.** The query says “P2pNccl KV transfer completion”, while the positive `audit-afd-p2p-exchanges` concerns hidden-state AFD exchanges and explicitly excludes KV-block release. P2pNccl/completion is related, but a hit cannot prove the full query was answered correctly. Keep the original 8-development-case label-hit score as a frozen diagnostic; any 7-source-valid-case subtotal must be separately named, never silently substituted.
2. **Held-out intent families are not fully disjoint.** Independently selected heldout02 and dev08 both concern `storage_io_measurement`. The four held-out queries/labels were unavailable during implementation and were not tuned, but this is unseen-query assessment, not family-disjoint generalization.
3. Positives are partial labels, not exhaustive corpus relevance judgments. No negative-ID labels were justified. No agent answer, actual hardware execution, or downstream task success is measured.

The timing query remains a valid fixed workload and output-parity check regardless of its label ambiguity. Efficiency-only optimization cannot establish improved relevance.
