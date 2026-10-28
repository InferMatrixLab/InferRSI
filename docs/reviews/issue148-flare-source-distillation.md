# Flare source distillation and evaluation plan

This is a bounded knowledge delivery for
[Issue 148](https://github.com/InferMatrixLab/InferRSI/issues/148), under the
source-distillation tracking goal. It is separate from the offline qualification
adapter. The source is NVIDIA/flare-local-inference at
`bce032c014bae34502ba22d3304fa084d5b40afe`; the public repository now resolves to
NVIDIA/local-inference at that same commit. The actual commit tree is
`f657cae770c66df9d6b47f9dbe8e40e14dc6fefa`.

## Construction and ownership

| Existing owner | Overlap decision | Delivered addition |
|---|---|---|
| [weight-loading-optimization](../../src/inferrsi/data/skill_library/methods/weight-loading-optimization/SKILL.md#10-separate-preparation-from-serving) | Generic loading/startup already has an owner | One preparation-boundary reference and typed Flare source; compilation/export/load/readiness/request phases stay distinct |
| [audit-vllm-kv-lifetimes](../../src/inferrsi/data/skill_library/repositories/vllm/audit-vllm-kv-lifetimes/SKILL.md) | Scheduler/connector lifetime concepts overlap, but concrete vLLM contracts differ | Related route only; no source or runtime replacement |
| [kv-tier-management](../../src/inferrsi/data/skill_library/repositories/lmcache/kv-tier-management/SKILL.md) | Tier policy overlaps, but LMCache MP configuration is not Flare's protocol | Related route only; no copied knobs or backend claims |
| [audit-flare-session-lifecycle](../../src/inferrsi/data/skill_library/repositories/flare-local-inference/audit-flare-session-lifecycle/SKILL.md) | Complete KV plus recurrent/convolution/tail state and scheduler-owned transfer tickets were not covered by those owners | One CUDA-scoped registered candidate with complete-state/fence/admission diagnostics |

The construction uses AREX-Skill
`ac3fe1afa80fb9a09775ecfb2b6cc3ba850a2db6` as a **method**, adapting its
source-anchor scope → ground → construct → verify process to InferRSI's native
owner, metadata, reader and generator contracts. The relevant source methods
are `distill-ml-knowledge`, `create-repo-skill` repository-evidence and
planning-and-writing, and `verify-repo-skill` usability-test-cases. This was
portable method use, not a DisCo CLI session, managed-library import, complete
AREX native verification or a new construction framework.

The anchor is source/task-agnostic; scoped capabilities are preparation
compatibility, complete restoration and admission/lifetime diagnosis. Strategy
is reuse-existing: the existing generic owner plus one Flare-specific owner.
The [20-file ledger](../../src/inferrsi/data/skill_library/repositories/flare-local-inference/audit-flare-session-lifecycle/references/source-ledger.json)
identifies exact bytes and inspected symbols/sections. Kernels, model recipes,
exporter implementation and unrelated repository areas are excluded. Upstream
scripts are reference-only: preparation and qualification require model/package,
CUDA and serving resources outside this source-only task. No executable helper
is copied or used to simulate native success.

The upstream server tests are retained as TEST-SOURCE. Running them requires
the real NVIDIA backend, compatible package/model and service process; CPU
imports or synthetic state cannot substitute. They are **not_run**, as are
native Flare, model/device/service validation and skill efficacy. InferRSI
reader/packaging checks establish delivery only. The source remains candidate;
no efficacy PASS or automatic promotion is proposed.

## Evaluation plan under the existing bounded workflow

Status: **not evaluated**; empirical validation: **not_run**. This plan follows
[bounded skill evaluation](../skill-evaluation.md) and
[Issue 88](https://github.com/InferMatrixLab/InferRSI/issues/88). It does not
authorize or schedule client calls.

Before execution, freeze the exact source/content/resource/dependency revisions
resolved by `KnowledgeReader`, development versus sealed cases, answer schema,
independent verifier, client/model/effort, condition order/repeats and time/token/
cost budget. Keep answers and verifier outside trial workspaces; record known
knowledge/history roots in the existing access audit. Invalid or incomplete
execution/grading remains INCONCLUSIVE, not a negative efficacy result.

The existing report-audit pilot driver has its own task schema; do not pass
Flare inputs to it and claim a run. A later authorized preparation should reuse
the lower-level `inferrsi.harness.skill_evaluation` bundle export, real-client
trial and summary contracts with a Flare-specific structured verifier. No
runner or paid execution is required to deliver this plan.

| Condition | Exposure | Question |
|---|---|---|
| N | No target skill or resources; same task facts and client | Baseline diagnosis |
| E-session | Complete Flare reader bundle | Correct application of complete-state, ticket/fence and outcome distinctions |
| E-preparation-old | Complete pre-update weight-loading bundle pinned below | Existing loading behavior and preparation diagnosis before this update |
| E-preparation-new | Complete updated weight-loading bundle pinned below, including its Flare reference | Incremental preparation ownership, independent-version and phase-accounting guidance |
| R | Both owners through native skill discovery | Relevant selection and avoidance of LMCache/vLLM contract substitution |

The new Flare session skill uses the matched **N / E-session** addition comparison.
The existing weight-loading owner uses **E-preparation-old / E-preparation-new**
to isolate this update; N alone is not its update baseline. Freeze the complete
owner sources, then record each native full-reader export and its resource
manifest/digest using the same frozen trusted exporter before authorized trials:

| Paired condition | Immutable owner source | Complete source resources |
|---|---|---|
| E-preparation-old | [Pre-update608](https://github.com/InferMatrixLab/InferRSI/tree/608df33683108b66ca497ec57a91fca559354a52/src/inferrsi/data/skill_library/methods/weight-loading-optimization) | All4 files: `SKILL.md`, `metadata.json`, `references/fastsafetensors-transfer-readset.md`, `references/llama-loading-readset.md` |
| E-preparation-new | [Updated3e6e](https://github.com/InferMatrixLab/InferRSI/tree/3e6ed45871696854c594071ae6e74203483c47e4/src/inferrsi/data/skill_library/methods/weight-loading-optimization) | All5 files: the updated `SKILL.md` and `metadata.json`, both existing readsets, and `references/flare-preparation-boundary.md` |

Both paired conditions use identical task inputs, full-target-bundle exposure
rules, access boundaries, answer schema, independent grader, client/model/effort
and environment. Only the target bundle version differs. Use fresh sessions,
balanced order/repeats and the same frozen cases; keep source scope and export
manifests explicit instead of substituting an abridged SKILL body or the current
mutable checkout for the old bundle. R remains a separate discovery probe.

Cross-owner navigation is not automatically exported by one reader bundle.
Declare every extra exposed bundle explicitly and retain the same condition
exposure for matched trials. A multi-owner integrated case should expose both
owners in its explicit condition rather than silently granting another source.

| Case / split | Evidence-backed input variation | Required structured oracle |
|---|---|---|
| Complete continuation / development | KV pages present; endpoint row absent; a descendant still needs the page-only node | Endpoint cannot restore; keep valid ancestor pages; do not declare full-chain deletion |
| Admission policy / development | Deep endpoint fails additional-token cost inequality; shorter endpoint passes | Both CostRejected and Admitted may occur; compute savings from consumed minus resident; no completed-reuse claim |
| Cancellation / sealed | Last waiter cancels after accepted enqueue, before completion | Ticket retains destinations/parent pin; require accounted completion/drain; separate logical cancellation from transfer cancellation |
| Restart/error / sealed | Namespace/layout mismatch, corrupt payload, and a permission-read failure as distinct inputs | Mismatch/corruption follows evidenced rejection/recompute path; unreadable file fails scan and is retained; no partial-state success |
| Existing loading accounting / sealed old-new pair | A pre-Flare startup report separates cold-cache loading, warmup and per-request measurements; warmup shapes do not match the requested shapes | Preserve existing owner sections1-2: retain source/format/placement/duplication and bytes/counts evidence, use startup wall-clock for fixed loading/warmup, keep per-request cost separate, and require warmup hit criteria; elapsed warmup alone does not prove a hit |
| Compatibility / sealed | Payload/carrier version looks familiar, but ABI or prepared contract differs | Require ABI 4 and prepared contract 2 and matching typed semantics; re-export, never retag handles |
| Measurement / sealed | Multiple tokens per SSE event and unrelated client/native absolute origins | Preserve groups, no invented per-token delivery interval, no cross-clock subtraction; core TTFT is not pure GPU prefill |
| Irrelevant route / sealed R probe | Ordinary LMCache MP retention configuration at its own pin | Route to existing LMCache owner; avoid imposing Flare's cost/ticket implementation |

Run the compatibility case and existing loading-accounting regression case
under both preparation versions with the same frozen task and oracle. Run the
session lifecycle and SSE-measurement cases under N/E-session; keep R selection
results separate. For old/new, report fixes, regressions, unchanged correctness,
uncovered cases and execution/grading errors per case, including retained older
capabilities; do not infer improvement from N/new alone.

These are proposed assertion-backed usability cases derived from the source;
their inputs and oracle files have not been executed by an evaluation client.
A verifier must check structured state-completeness, admissibility, owner,
release precondition, clock domain and source keys. Nonempty explanatory prose
alone is not a correctness oracle. Preserve neutral/negative answers and unknown
usage/cost; rotate matched condition order to avoid the historical position
imbalance. Report per-case correctness, discovery, trial errors, observed usage
and descriptive elapsed time separately. A future behavioral pass does not
establish native cache correctness or hardware/service performance.
