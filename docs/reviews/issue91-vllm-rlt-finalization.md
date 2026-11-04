# vLLM-RLT synchronous KV finalization

Related to #91. This is one source-derived candidate capability, extending the descriptor-only [intake](issue91-vllm-rlt-intake.md) without replacing its historical evidence.

## Construction record

The source anchor is `InferMatrixLab/vllm-rlt@4a350344027960a48384626aa646f1765fda6d4f`, tree `4c2cab1f497513ea0590060eb53ee0b179a5bf70`. The approved scope is synchronous native Ouro with host `KVMetadata`: LAST_EXITED propagation versus SHARED, later attention consumption, and normal release/wait/free order. Asynchronous preemption/speculation, device-owned metadata, transfer/prefix ownership, capacity estimation and whole-engine extraction are excluded.

Portable AREX `distill-ml-knowledge` scope → ground → construct → verify informs the direct, task-agnostic source construction. The existing `extend-repo-skill` ownership check found no RLT operating owner; the separately approved `audit-recurrent-kv-finalization` capability is the only new node. InferRSI's existing typed metadata, canonical library, registry and readers are the packaging contract. No DisCo managed import, extra router, dependency installation or evaluation framework is introduced.

The grounded evidence is the intake's bounded manager/runner/test/license material plus the fixed caller, request, metadata, Ouro consumer and Torch dispatch tuple. The [source notes](../../src/inferrsi/data/skill_library/repositories/vllm-rlt/audit-recurrent-kv-finalization/references/source-notes.md) explain the call chain and exclusions; the [file ledger](../../src/inferrsi/data/skill_library/repositories/vllm-rlt/audit-recurrent-kv-finalization/references/source-identity.json) records exact Git blobs, SHA256, ranges and carried versus added acquisition. The original Apache-2.0 LICENSE and model/configuration NOTICE bytes are retained. No implementation or model weights are copied.

```mermaid
flowchart LR
    A["Pinned manager, scheduler, runner, Ouro and metadata sources"] --> B["One candidate procedure + source ledger + notices"]
    B --> C["Existing registry and library navigation"]
    C --> D["skills / checkout reader: complete local resources"]
    C --> E["Stock projection from committed canonical source"]
    E --> F["catalog / package reader"]
```

The two rules are narrow: copy the final executed recurrent-layer K/V into skipped LAST_EXITED planes before a later deeper history read; retain the last completion dependency until runner release precedes cache-reference reclamation. The procedure preserves allocated-capacity, written-validity, copied-data and completed-work distinctions. SHARED is a single-plane control; bookkeeping-only `mark_finalized` is not a copying substitute. Backend placement is navigation, not qualification.

## Proposed representative and regression cases

These are candidate inputs and expected discriminators, not results. Native tests use the original package and real Torch tensors. An absent/new skill comparison can use the same questions, without changing the engine, inputs or expected source contract.

| Case | Positive / negative discriminator | Grounded input |
|---|---|---|
| Executed-plane regression | Preserve shallower/executed K/V; deeper propagation is a physical copy, not an alias | Upstream `test_last_exited_copies_every_layer_and_preserves_executed_depths`, 38–58 |
| Later deeper attention | Finalized earlier tokens remain readable as later tokens reach deeper planes across a block boundary | `test_early_exit_then_later_token_loops_deeper_across_block_boundary`, 61–77 |
| Premature finalize / prefix gap | Allocated capacity or a sparse later write must not make missing history valid | `test_validation_happens_before_mutation`, 97–107; `test_out_of_order_writes_only_expose_complete_prefix`, 116–127 |
| Bookkeeping sentinel | `mark_finalized` preserves deeper sentinels; `finalize_token` performs the copy | `test_mark_finalized_records_deeper_planes_without_copying`, 216–233 |
| SHARED control | One plane serves every depth; do not expect LAST_EXITED isolation or extra propagation | `test_shared_layout_exposes_one_plane`, 168–174; `test_mark_finalized_is_a_no_op_for_shared_layout`, 245–258 |
| Reused-page regression | A new request cannot consume stale old-request bytes merely because pages are reused | `test_block_reuse_never_exposes_stale_request_history`, 80–94 |
| Retirement investigation | Identify the latest event and release wait before scheduler finish/free; recording alone is insufficient | Runner 1331–1375; engine 626–640; scheduler 181–193 |
| Unsupported-path counterexample | Refuse to qualify async/device-owned metadata from host-prefix checks or synchronous call order | README 70–75; metadata 45–54; manager 716–727 |

All test names above are in the pinned upstream `tests/test_kv_cache.py`. Its manager tuple is CPU/float32/Torch attention, 2 layers, 1 KV head, head dimension 4, 18 blocks, block size 2 and 3 loops. The package initializer and test conftest require real Torch. The available construction environment lacks Torch and other declared CPU dependencies, so upstream import and native CPU tests are **not_run**; no classes, tensors or formulas were substituted. This is a concrete execution gap, not a correctness failure.

## Verification boundaries and handoff

Schema/frontmatter, registry navigation, source identity/ranges, local resource links, retained notices, checkout reads and deterministic catalog generation are content/package checks. Matching package reads and source hashes must be checked on the real generated child of the committed canonical source. They establish access and provenance, not RLT runtime correctness.

Native CPU/CUDA, model output equivalence, quality, performance and agent efficacy remain **not_run / not evaluated**. CPU cache tests cannot establish CUDA completion. The existing asynchronous-output/cleanup warnings remain unresolved. Candidate maturity and `empirical_validation=not_run` are preserved independently of software checks or merge status.

Author: Codex / gpt-6.1-sol / xhigh. Independent review, final source/generated commit identities and actual check receipts belong to the revision-scoped PR. Governing tracking Issue closure is not claimed.
