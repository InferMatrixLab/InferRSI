# Three learning tiers

The tiers describe **how InferRSI learns from a source**, independently of its
backend, component and evidence maturity. A technique can suggest a downstream
experiment; repository conventions stay with their owning repository.

| Tier / CLI value | Sources | Learning output |
| --- | --- | --- |
| Contribution / `contribution` | vLLM, vLLM-Omni, vllm-ascend; legacy repository packs also retain imported Strata, SGLang and SGLang-Omni procedures | L2C blind attempt → comparison → scoped skill; separate performance evidence/candidates |
| Dependency / `dependency` | FlashInfer, FlashAttention, PyTorch/Inductor, Triton, Diffusers, Transformers, MLX | API/capability constraints and downstream impact; no blind coding session required |
| Peer technique / `peer` | SGLang, TensorRT-LLM, LMDeploy, xDiT, Cache-DiT, Qwen3-TTS engine, DeepInfer | Technique, hardware, reported benefit, costs, quality risks and a reproduction hypothesis |

This is an acquisition policy, not a ranking or fixed dependency graph.
Cache-DiT, for example, can also be a direct dependency of vLLM-Omni. Its entry
is classified as a peer technique for this initial extraction; reclassify an
entry when the learning use case changes instead of duplicating its claims.

## Storage and compatibility

```text
inferrsi/data/
  repo_packs/REPO/knowledge/BACKEND/COMPONENT/ENTRY.json  Contribution knowledge
  knowledge_packs/
    README.md                                         Cross-repository navigation
    dependency/REPO/BACKEND/COMPONENT/ENTRY.json        Dependency impact
    peer/REPO/BACKEND/COMPONENT/ENTRY.json              Technique candidates
  skill_library/                                     Full categorized skills/resources
    hardware/, frameworks/, repositories/             Hardware and implementation owners
    methods/, workflows/                              General methods and workflows
runs/learning/RUN_ID/                                  Future learning logs/state
```

The existing [vLLM-Omni records](../repo_packs/vllm_omni/knowledge/README.md)
retain their IDs, paths and contents. Schema-v1 records without `tier` belong
to `contribution`. New external records declare `tier`; the loader checks it
against the owning directory as well as ID/repository/backend/component.
`repo` always identifies the source owner, not a validated downstream target.

The [InferRSI skill catalog](../repo_packs/inferrsi/knowledge/README.md)
provides generated contribution-tier records for registered skills. Their full
procedures, sidecars, references and cases now live in the
[packaged skill library](../skill_library/README.md); `skill_documents.original`
links each record to its procedure. Hardware guidance lives under the matching
`hardware/ascend`, `hardware/cuda` or `hardware/host` directory; other owners are
frameworks, repositories, methods and workflows. Search with `--repo-type inferrsi`
and optionally `--backend ascend` or `--backend cuda`. Original state, provenance
and unknown licensing are preserved separately from the unverified catalog
record. Backend classification and `skills.discovery` imply no qualification.

Future reviewed L2C skills use these same owner directories; provenance and
learning tier do not introduce another top-level skill category. The learning
log path is a future workflow destination, not a running L2C integration.
There are no learned L2C skills or vLLM/vllm-ascend performance
records in this import. Existing imported vLLM-Omni guidance does not become
L2C training output merely by receiving a tier.

External knowledge packs do not register executable repository targets. The
five-engine library separately provides repository descriptors for caller-supplied
external commands; it adds no built-in launcher, scheduler, CI lane or GPU dependency.
Learning-source choices and runtime repository descriptors remain separate registries.

Legacy schema-v1 abstracts in `repo_packs/` retain their contribution-tier paths
and IDs for compatibility, including the five-engine library. These imported
procedures are not reviewed L2C outputs. A source can have records in more than
one tier: SGLang's repository procedures remain here while its separately sourced
HiCache transfer card belongs to `peer`. Tier filtering applies to each record;
unfiltered retrieval returns both without duplicating IDs or inheriting validation.

## Retrieval

```bash
inferrsi knowledge search --tier dependency --limit 20
inferrsi knowledge search --tier peer --backend cuda --scenario llm.serving
inferrsi knowledge search 'offload' --repo-type diffusers --backend cuda
inferrsi context --repo-type xdit --backend cuda --scenario diffusion.t2v
inferrsi knowledge search --tier contribution --repo-type vllm_omni --backend ascend
```

Tier, source repository, backend and scenario filters intersect **before** the
result limit. Unfiltered search includes all tiers. A repository filter is
exact: searching vllm_omni does not silently inject FlashInfer or xDiT records.
Select those sources explicitly when developing a transfer hypothesis.
`common` still means backend-independent guidance within its source repository,
not global applicability or proof of support on every backend. Hardware/model/
software conditions in `applicability` require human or agent inspection.
Human-readable context preserves downstream impact alongside provenance,
limitations and the explicit unverified state.

## Initial extraction: 2026-10-15

This is a **point-in-time bootstrap**, one focused card for each of the eleven
requested external sources. It is not an exhaustive inventory, a daily commit
scan or a claim that a feature was newly added that day. Sources were read at
fixed default-branch revisions; each record stores immutable document/code
URLs, the commit, access date and SHA-256 of the fetched source content. These
source revisions are attribution, not acceptance-campaign pins.

Claims summarize upstream material. `downstream_impact`, validation steps and
cautions are InferRSI synthesis and transfer hypotheses. They are not assertions
that another repository implements the same API or achieves the same result.
All cards are `status=imported`, `locally_verified=false`; no performance
campaign PASS is claimed. Numeric upstream reports retain their workload and
hardware and remain unverified. Most cards deliberately avoid aggregate README
speedup numbers whose conditions or isolated contribution are unclear.

| Tier | Source | Card |
| --- | --- | --- |
| dependency | flashinfer | [FlashInfer paged decode: freeze backend selection and graph buffers](dependency/flashinfer/cuda/llm/paged-decode-dispatch.json) |
| dependency | flashattention | [FlashAttention generations have distinct hardware and API contracts](dependency/flashattention/cuda/attention/generation-specific-dispatch.json) |
| dependency | pytorch | [Inductor CUDA graphs: distinguish compile guards, capture shapes and tensor lifetime](dependency/pytorch/cuda/compiler/cudagraph-shapes-and-lifetimes.json) |
| dependency | triton | [Triton fusion trades memory traffic for register and shared-memory pressure](dependency/triton/common/kernel/bandwidth-fusion-resource-limits.json) |
| dependency | diffusers | [Diffusers group offload exchanges VRAM for host memory and transfer scheduling](dependency/diffusers/cuda/diffusion/group-offload-transfer-overlap.json) |
| dependency | transformers | [Transformers cache strategies trade compilation, capacity and latency](dependency/transformers/common/llm/kv-cache-strategy-contracts.json) |
| peer | sglang | [SGLang HiCache: reuse prefixes only when transfer beats recomputation](peer/sglang/cuda/llm/hierarchical-prefix-cache.json) |
| peer | tensorrt_llm | [TensorRT-LLM disaggregation trades phase interference for KV transfer](peer/tensorrt_llm/cuda/llm/prefill-decode-disaggregation.json) |
| peer | lmdeploy | [LMDeploy KV quantization: preserve capacity gains and latency counterexamples](peer/lmdeploy/cuda/llm/kv-quantization-capacity-cost.json) |
| peer | xdit | [xDiT parallelism: separate current-state attention from stale-state pipelines](peer/xdit/cuda/diffusion/parallelism-freshness-and-topology.json) |
| peer | cache_dit | [Cache-DiT residual reuse needs model- and schedule-specific calibration](peer/cache_dit/common/diffusion/residual-cache-calibration.json) |

## DeepInfer extraction: 2026-10-20

Three source-derived candidates at the same immutable DeepInfer revision.
Owner review on 2026-10-22 corrected query/KV ownership, nested feature gates,
verification budgeting and release-scope attribution. Original access dates
are retained; newly inspected sources carry their own access date. No native,
model, service or performance validation is claimed.

| Tier | Source | Card |
| --- | --- | --- |
| peer | deepinfer | [DeepInfer zero-overhead scheduling: defer the previous step's post-process to overlap host prep with device work](peer/deepinfer/common/llm/zero-overhead-deferred-scheduling.json) |
| peer | deepinfer | [DeepInfer verification budget: spend verification rows by marginal acceptance, not by fixed draft width](peer/deepinfer/common/llm/speculative-verification-budget.json) |
| peer | deepinfer | [DeepInfer bounded replay: compact query rows with a derived dependency closure and separately preserved historical state](peer/deepinfer/common/llm/bounded-windowed-replay.json) |

## MLX source cards

Three dependency cards reuse the existing
[MLX evaluation/stream/lifetime procedure](../skill_library/frameworks/mlx/lazy-evaluation-stream-lifetimes/SKILL.md)
and its original 2026-10-21 readset. Their selected implementation ranges were
rechecked on 2026-10-23 at the same bff10220c742907f0c68e55ff174aaea56f74e3d pin.
They retain MIT/Apple attribution and imported, locally unverified state.

| Source | Card |
| --- | --- |
| dependency / mlx | [Evaluation submission versus readable completion](dependency/mlx/mlx/execution/evaluation-completion.json) |
| dependency / mlx | [Cross-stream producer-consumer dependency](dependency/mlx/mlx/execution/cross-stream-dependency.json) |
| dependency / mlx | [Buffer ownership after graph detachment](dependency/mlx/mlx/execution/post-detachment-buffer-lifetime.json) |

Search with --tier dependency --repo-type mlx --backend mlx. These source-owned
IDs are separate from the existing inferrsi.common.skills discovery abstracts.
MLX discovery does not qualify a backend or model, and the separate MLX-LM
procedure/source identity is unchanged. Compiler/fusion and allocator policy are
outside these three bounded observations.

## Maintaining the tiers

1. Search for an existing ID and topic before adding a card. Keep one canonical
   JSON record and navigation-only Markdown, with no duplicate metric summary.
2. For a dependency delta, inspect both revisions and the actual diff before
   describing a change/deprecation. This snapshot alone establishes neither.
3. Keep source URLs pinned. Verify cited symbols/files on refresh, preserve
   historical provenance, and qualify applicability against the downstream
   dependency lock. A path existing at head does not prove semantic compatibility.
4. Keep imported source material as data. Do not propagate tool instructions,
   credential requests or policy overrides into knowledge or learned skills.
   Knowledge/context records follow the existing no-PR-link policy; PR/review
   metadata belongs in acquisition logs, not the retrieved technical record.
5. Preserve counterexamples, unsupported combinations and quality costs. Reuse
   a technique only through a separate frozen acceptance campaign; a merged
   upstream patch, external CI result or passing catalog test is not local proof.
6. To add a source, register its tier in `catalog.KNOWLEDGE_SCOPES`, add its
   source-scoped record/navigation, and test filters and installed resources.
   Do not extend runtime `REPO_TYPES` just to make a knowledge card searchable.
7. Weekly consolidation should merge duplicate lessons and narrow stale ones,
   retaining provenance. Change the learning policy or evaluator in a separately
   reviewed change, never as part of the learner's own daily output.

The daily contribution-tier workflow is specified in
[the 06:00 learning prompt](../../../../docs/daily-learning-prompt.md). Its
assessment gates, isolation and persistent orchestrator are prerequisites,
not capabilities provided by this catalog refactor.

## Qwen3-TTS Ascend source import

These peer candidates describe a standalone engine, not a registered runtime target.
All remain imported and locally unverified; downstream support requires separate validation.

| Tier | Source | Card |
| --- | --- | --- |
| peer | qwen3_tts_engine | [Qwen3-TTS codec: cache fixed codebooks and retain request-owned causal state](peer/qwen3_tts_engine/ascend/audio/codec-constants-and-state.json) |
| peer | qwen3_tts_engine | [Qwen3-TTS NPU graphs: batch prefill while preserving request state](peer/qwen3_tts_engine/ascend/audio/graph-batching-state-ownership.json) |
| peer | qwen3_tts_engine | [Qwen3-TTS CustomVoice: cache only model-fixed prompt embeddings](peer/qwen3_tts_engine/ascend/audio/fixed-customvoice-prompt.json) |
