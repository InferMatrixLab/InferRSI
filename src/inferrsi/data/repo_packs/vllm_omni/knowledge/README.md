# vLLM-Omni knowledge

This is the contribution tier of the [three-tier knowledge catalog](../../../knowledge_packs/README.md).
The external dependency and peer tiers have separate source owners; existing
records here keep their IDs, paths and verification state.

Each named JSON file is the canonical catalog record for one reusable experience
or source-guided topic. This README provides organization and navigation rather
than a second per-entry summary. Existing experience records retain their IDs
and source history. New topic abstracts link to complete English procedures
through `skill_documents`.

Full library: [English skill](../../../skill_library/repositories/vllm-omni/SKILL.md).

## Ownership and hierarchy

```text
data/
  repo_packs/<repo>/
    pack.json                         Repository capabilities
    knowledge/
      README.md                       This guide and entry links
      common/<component>/<entry>.json Backend-independent methods
      cuda/<component>/<entry>.json   CUDA-scoped experience
      ascend/<component>/<entry>.json Ascend-scoped experience
  platform_packs/<backend>/pack.json   Backend inspection and capabilities
evidence/<campaign>/                   Frozen plans, artifacts and verdicts
```

Only directories with records are created. This pack covers diffusion,
multi-stage orchestration (`omni`) and streaming audio. `common` means common
**within that repository**, not globally validated across repositories. ROCm
currently retrieves common methods only. There are no ROCm-specific
optimization results in this pack.

| Axis | Stored in | Meaning |
| --- | --- | --- |
| Repository ownership | repo directory and repo field | Prevents mixing repositories |
| Backend scope | backend directory and backend field | common or one concrete backend |
| Component | component directory and component field | Diffusion, omni orchestration or audio |
| Workload | scenario | Exact image/video scenario or a component wildcard |
| Model and prerequisites | applicability and tags | Model, SKU, software, shapes, dtype and workload conditions |
| Origin and maturity | status, sources, verification | Imported guidance/report versus locally supported evidence |

A model is a field rather than another directory level: a shared method can
apply to several models without copying records. Keep an entry ID stable.
Add a separate record when another backend needs different prerequisites,
failure modes or measurements; do not overwrite the original qualification.

## Record contract and retrieval

Every record carries its ID/title/summary, repository/backend/component/scenario,
schema_version, import status, source attribution and explicit verification.
Applicability, claims, recommendations, validation_plan and limitations hold
the technical content. The loader checks path/ID/scope consistency and pinned
source attribution before making a record available.

The CLI reads JSON directly; it never parses this README or executes imported
instructions. Repository, backend and scenario filters run before keyword
matching and the result limit. A backend query includes that backend plus
common methods. Scenario aliases diffusion.t2i and diffusion.t2v still work.
Hardware/model/software conditions require inspection of applicability; they
are not an automatic eligibility check.

```bash
inferrsi knowledge search --repo-type vllm_omni --backend ascend --scenario diffusion.t2i
inferrsi knowledge show vllm_omni.ascend.diffusion.qwen_image_21_eager_t2i
inferrsi context --repo-type vllm_omni --backend cuda --scenario diffusion.image_generation
```

Human-readable context is rendered from the same JSON used by search/show.
When present, `skill_documents` identifies package-relative paths to the full
English skills, which contain detailed procedures and source maps.
Those skills are the source material for the concise indexed abstract, not a
second per-entry catalog summary. This entry list contains navigation only;
tests check that every packaged record is listed.

## Entries

| Backend | Record |
| --- | --- |
| ascend | [MiniMax-H3 reference KV reuse must balance ownership after Ulysses](ascend/diffusion/minimax-h3-reference-kv-reuse.json) |
| ascend | [MiniMax-H3 SP head buckets reduce exposed All-to-All with quality still pending](ascend/diffusion/minimax-h3-sp-head-buckets.json) |
| ascend | [Qwen-Image-2.1 eager text-to-image on one 910B1: reuse plus interleaved RoPE, 30% not met](ascend/diffusion/qwen-image-21-eager-t2i.json) |
| common | [vLLM-Omni streaming audio, deployment and measurement boundaries](common/audio/streaming-serving-measurement.json) |
| common | [Diffusion measurement and profiling discipline](common/diffusion/measurement-and-profiling.json) |
| common | [Production diffusion integration and compatibility gates](common/diffusion/production-integration-gates.json) |
| common | [vLLM-Omni diffusion step state and output/transport validation](common/diffusion/step-state-and-output-validation.json) |
| common | [Upstream review gates for optional acceleration and evidence ownership](common/diffusion/upstream-review-gates.json) |
| common | [vLLM-Omni stage ownership and constrained execution search](common/omni/stage-ownership-and-search.json) |
| cuda | [Qwen3-Omni MRv2 existing optimizations and streaming measurement boundaries](cuda/audio/qwen3-omni-mrv2-measurement-and-tuning.json) |
| cuda | [Audio concurrency scaling: mixed prefill, state ownership and codec overlap](cuda/audio/concurrency-scaling-state-and-overlap.json) |
| cuda | [MiniMax-H3 exact AdaLN schedule cache: capacity benefit can exceed latency benefit](cuda/diffusion/minimax-h3-adaln-schedule-cache.json) |
| cuda | [MiniMax-H3 online CUDA MXFP8 is an opt-in approximate deployment lane](cuda/diffusion/minimax-h3-cuda-mxfp8.json) |
| cuda | [MiniMax-H3 modulation fusion changes rounding and requires platform guards](cuda/diffusion/minimax-h3-fp32-modulation.json) |
| cuda | [MiniMax-H3 guarded Q/K RMSNorm and packed RoPE fusion](cuda/diffusion/minimax-h3-qk-norm-rope.json) |
| cuda | [MiniMax-H3 Ref2VA TeaCache needs task-specific calibration and step defaults](cuda/diffusion/minimax-h3-ref2va-teacache.json) |
| cuda | [MiniMax-H3 stacked VAE tiling trades activation memory for fewer decode calls](cuda/diffusion/minimax-h3-vae-stacked-tiling.json) |

## Attribution and evidence

Knowledge records and exported context contain no PR or review-thread links.
Keep repository/revision/date attribution, known authors and immutable
technical-document URLs. A repository URL plus a commit identifies the source
context; it is **not** a link to raw measurement evidence. Review guidance is
attributed to its reviewed source revision and remains guidance.

All current entries remain status=imported and
verification.locally_verified=false. Evidence levels describe content:
guidance or upstream_reported. Source merge/open status, where retained, is a
historical observation at accessed_at; it is not a confidence level.
Removing links and reorganizing files does not verify any performance claim.

Reported numbers and counterexamples retain their hardware, workload, quality
and sampling limits. Missing raw outputs or frozen validators remain explicit.
Campaign artifacts belong in evidence/ and run directories; knowledge stores
the reusable lesson and its boundaries.

## Maintaining the pack

1. Find an existing entry by topic and scope before adding a new file. Use a
   concise slug and match its repo.backend.component.slug_with_underscores ID.
2. Write conditions, the actionable lesson, validation steps, limitations and
   negative results in JSON. Attribute known authors; omit PR links.
3. Keep imported claims unverified. Local qualification requires a separate
   frozen campaign with exact source/environment/workload and complete quality
   and performance artifacts. CPU tests, a merged change or a source report
   alone do not promote an entry.
4. When new evidence narrows or contradicts a lesson, update its conditions and
   limitations without erasing the negative result or reassigning its ID.
   Preserve the historical campaign artifacts.
5. Add a navigation row here, then run the catalog/CLI tests and the
   noneditable-package resource check. No manual index of metrics is needed.
6. For a topic backed by the full skill library, retain valid `skill_documents`
   paths to English procedures and reconcile the concise abstract when the
   detailed source contracts change. Do not replace or silently repin historical records
   while adding a newer source snapshot.

Repository-wide and backend-wide methods stay in their owning packs. External
dependency and peer techniques have explicit source/tier filters in the
three-tier catalog; common is never an implicit global inheritance mechanism.
