# Diagnostic result and validation ledger

Campaign verdict: INCONCLUSIVE. No performance benchmark acceptance performed.

| Attempt | Scope | Observed outcome | Allocation |
| --- | --- | --- | --- |
| 1924 | Observer v1 identity | Execution failed before loading; optional FlashInfer package metadata incorrectly required. Preserved. | 1 GPU x 6 s |
| 1925 | Unchanged-source three-path contrast | Buffered eager/replay logits and state exact 48/48; compact prefill differed 3/3. | 1 GPU x 82 s |
| 1926 | Configured-backend/API CPU regression | 78 passed. | 0 GPU |
| 1933 | Prefill/model CPU regression | 26 passed. | 0 GPU |
| 1935 | Model-only prefill repair, same diagnostic inputs | Prefill exact 3/3; buffered/replay exact 48/48; compact/buffered decode exact 35/48, greedy choices equal 48/48. | 1 GPU x 59 s |
| 1937 | Combined repair full Qwen CPU suite | 156 passed, 1 GPU contract test skipped. | 0 GPU |
| Local | Synthetic runner/service/entry regression | 58 passed. | 0 GPU |
| Local | InferRSI evidence inventory tests | 17 passed. | 0 GPU |
| Local | Extra lint of executed observer snapshot | I001 import grouping and E501 long line; archival bytes retained, not rewritten after execution. | 0 GPU |

Allocated GPU total: 147 seconds = 0.040833 GPU-hours. All listed Slurm jobs
completed or failed with known exit status and released their allocations.
Runtime dependencies were not changed. The exact diagnostic observer is
retained under validator/diagnostics with corresponding recorded source digests;
it is an instrumented numerical diagnostic, not a performance validator.

The source snapshots bind runtime bytes; model config/index metadata was
rechecked, while this short diagnosis reused earlier full checkpoint-byte
authentication. It did not rehash all weight shards. Final acceptance must
apply its complete prospective identity-validation policy.

Recorded KnowledgeStore candidates, with verified retained-content readback:

- `store:case.qwen38-fp8-dispatch-provenance-takeover-cand`
  revision `sha256:20839f9b731e1f9f8ec2bcaba570d1e38f39aa3e64c4c0d63d4e3105cfec4c48`.
- `store:case.qwen38-graph-prefill-layout-takeover-cand`
  revision `sha256:fc9e38fcd98a6d79a73f6fc9967a8bfc82fc261f9bbda776e520cd80086be3fc`.

These are local store-owned candidate bundles; no repository promotion,
acceptance Issue closure, engine merge or production release is implied.
