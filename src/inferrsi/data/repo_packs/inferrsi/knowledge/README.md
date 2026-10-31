# InferRSI skill discovery index

Generated abstracts for all 77 registered skills in `data/skill_library/`.
Their complete procedures, references and cases ship in the same package.
`skill-index.json` maps stable skill IDs to categorized directories. The
reference and searchspace matrices
remain the maintained knowledge views. Do not edit generated files by hand.

Index status `imported` and `locally_verified: false` describe these discovery
records. Original status, provenance, license declarations and limitations
are preserved under `skill_metadata`; absent fields remain absent. Unknown
licenses remain unknown. Indexing grants no execution permission or validation.

These are knowledge abstracts (`--kind knowledge`), with namespaced package
IDs distinct from explicitly selected `checkout_ref` skills. Ascend/CUDA
procedures use their corresponding backend; shared methods use `common`.

Source snapshot: [b3c091a61e128cb848ca826d2fdc6b8f9d10e6ff](https://github.com/InferMatrixLab/InferRSI/tree/b3c091a61e128cb848ca826d2fdc6b8f9d10e6ff/src/inferrsi/data/skill_library).

```bash
inferrsi knowledge search 'profiling' --repo-type inferrsi --limit 50
inferrsi collect --repo-type inferrsi --kind knowledge --limit 50 --material
```

After committing changes to skill bodies, resources or the registry, regenerate from a
development installation with the skills extra. The source revision must
contain the current input paths and bytes (Git checkout filters are respected).
`source_files` hashes identify the canonical Git bytes, not a validation result.

```bash
python tools/build_skill_index.py --source-revision <committed-source-revision>
python tools/build_skill_index.py --source-revision b3c091a61e128cb848ca826d2fdc6b8f9d10e6ff --check
```

`--check` detects missing, stale and unexpected generated records without writing.
References and cases ship with their owning skill, not as duplicate knowledge abstracts.

| Skill | Backend | Original declared status |
| --- | --- | --- |
| [ascend-aclgraph-capture-replay](ascend/skills/ascend-aclgraph-capture-replay.json) | ascend | candidate |
| [ascend-device-health](ascend/skills/ascend-device-health.json) | ascend | candidate |
| [ascend-distributed-parallel](ascend/skills/ascend-distributed-parallel.json) | ascend | candidate |
| [ascend-graph-mode](ascend/skills/ascend-graph-mode.json) | ascend | candidate |
| [ascend-model-adaptation](ascend/skills/ascend-model-adaptation.json) | ascend | candidate |
| [ascend-operator-profiling](ascend/skills/ascend-operator-profiling.json) | ascend | candidate |
| [ascend-operator-tuning](ascend/skills/ascend-operator-tuning.json) | ascend | candidate |
| [ascend-optimization-casebook](ascend/skills/ascend-optimization-casebook.json) | ascend | candidate |
| [ascend-performance-analysis](ascend/skills/ascend-performance-analysis.json) | ascend | candidate |
| [ascend-video-diffusion-optimization](ascend/skills/ascend-video-diffusion-optimization.json) | ascend | candidate |
| [ascendc-tiling-design](ascend/skills/ascendc-tiling-design.json) | ascend | candidate |
| [assess-serving-preemption](common/skills/assess-serving-preemption.json) | common | candidate |
| [assess-split-backward-schedule](common/skills/assess-split-backward-schedule.json) | common | candidate |
| [audit-afd-p2p-exchanges](cuda/skills/audit-afd-p2p-exchanges.json) | cuda | candidate |
| [audit-fixed-workload-claim](common/skills/audit-fixed-workload-claim.json) | common | candidate |
| [audit-flare-session-lifecycle](cuda/skills/audit-flare-session-lifecycle.json) | cuda | candidate |
| [audit-h3-metal-fasth3-semantics](common/skills/audit-h3-metal-fasth3-semantics.json) | common | candidate |
| [audit-h3-runtime-residency](common/skills/audit-h3-runtime-residency.json) | common | candidate |
| [audit-llama-runtime-state](common/skills/audit-llama-runtime-state.json) | common | candidate |
| [audit-recurrent-kv-finalization](common/skills/audit-recurrent-kv-finalization.json) | common | candidate |
| [audit-sd-cpp-residency](common/skills/audit-sd-cpp-residency.json) | common | candidate |
| [audit-sglang-diffusion-lifetimes](common/skills/audit-sglang-diffusion-lifetimes.json) | common | candidate |
| [audit-vllm-kv-lifetimes](common/skills/audit-vllm-kv-lifetimes.json) | common | candidate |
| [bound-windowed-attention-replay](common/skills/bound-windowed-attention-replay.json) | common | candidate |
| [budget-speculative-verification](common/skills/budget-speculative-verification.json) | common | candidate |
| [calibrate-serving-simulation](common/skills/calibrate-serving-simulation.json) | common | candidate |
| [cann-attribution-overlap](ascend/skills/cann-attribution-overlap.json) | ascend | candidate |
| [cgroup-resource-controls](common/skills/cgroup-resource-controls.json) | common | candidate |
| [checkpoint-recovery-consistency](common/skills/checkpoint-recovery-consistency.json) | common | candidate |
| [choose-parallel-training-plan](common/skills/choose-parallel-training-plan.json) | common | candidate |
| [cite-check-downstream-pr](common/skills/cite-check-downstream-pr.json) | common | candidate |
| [claim-contract](common/skills/claim-contract.json) | common | candidate |
| [comfy-ui](common/skills/comfy-ui.json) | common | candidate |
| [competitor-scan](common/skills/competitor-scan.json) | common | candidate |
| [dcp-async-save-performance](common/skills/dcp-async-save-performance.json) | common | candidate |
| [dense-performance-evidence](common/skills/dense-performance-evidence.json) | common | candidate |
| [diagnose-attention-bottlenecks](cuda/skills/diagnose-attention-bottlenecks.json) | cuda | candidate |
| [diagnose-vllm-admission-pressure](common/skills/diagnose-vllm-admission-pressure.json) | common | candidate |
| [diffusers-invocation-state](common/skills/diffusers-invocation-state.json) | common | candidate |
| [draft-acceptance-issue](common/skills/draft-acceptance-issue.json) | common | candidate |
| [dwarfstar](common/skills/dwarfstar.json) | common | candidate |
| [evaluate-elastic-serving-placement](common/skills/evaluate-elastic-serving-placement.json) | common | candidate |
| [generation-cache-lifecycle](common/skills/generation-cache-lifecycle.json) | common | candidate |
| [host-memory-management](common/skills/host-memory-management.json) | common | candidate |
| [host-overhead-optimization](common/skills/host-overhead-optimization.json) | common | candidate |
| [host-overhead-profiling](cuda/skills/host-overhead-profiling.json) | cuda | candidate |
| [husky](common/skills/husky.json) | common | candidate |
| [inference-benchmark-design](common/skills/inference-benchmark-design.json) | common | candidate |
| [inference-optimization-casebook](common/skills/inference-optimization-casebook.json) | common | candidate |
| [kernel-writing-guide](common/skills/kernel-writing-guide.json) | common | candidate |
| [kv-tier-management](common/skills/kv-tier-management.json) | common | candidate |
| [lazy-evaluation-stream-lifetimes](common/skills/lazy-evaluation-stream-lifetimes.json) | common | candidate |
| [lily](common/skills/lily.json) | common | candidate |
| [lithos-metal](common/skills/lithos-metal.json) | common | candidate |
| [local-dream](common/skills/local-dream.json) | common | candidate |
| [mistral-rs](common/skills/mistral-rs.json) | common | candidate |
| [mlc-llm](common/skills/mlc-llm.json) | common | candidate |
| [mlx-swift-lm](common/skills/mlx-swift-lm.json) | common | candidate |
| [npu-skill-factory](common/skills/npu-skill-factory.json) | common | candidate |
| [optimization-search-policy](common/skills/optimization-search-policy.json) | common | candidate |
| [os-process-placement](common/skills/os-process-placement.json) | common | candidate |
| [performance-ceiling-analysis](common/skills/performance-ceiling-analysis.json) | common | candidate |
| [plan-activation-residency](common/skills/plan-activation-residency.json) | common | candidate |
| [project-maya](common/skills/project-maya.json) | common | candidate |
| [reason-hopper-kernels](cuda/skills/reason-hopper-kernels.json) | cuda | candidate |
| [repository-evolution-analysis](common/skills/repository-evolution-analysis.json) | common | candidate |
| [rsi-evidence](common/skills/rsi-evidence.json) | common | candidate |
| [skill-evolution-playbook](common/skills/skill-evolution-playbook.json) | common | candidate |
| [splash](common/skills/splash.json) | common | candidate |
| [storage-io-measurement](common/skills/storage-io-measurement.json) | common | candidate |
| [torchnpu-device-memory-lifecycle](ascend/skills/torchnpu-device-memory-lifecycle.json) | ascend | candidate |
| [torchnpu-pinned-host-memory-lifecycle](ascend/skills/torchnpu-pinned-host-memory-lifecycle.json) | ascend | candidate |
| [training-input-pipeline](common/skills/training-input-pipeline.json) | common | candidate |
| [training-resource-budget](common/skills/training-resource-budget.json) | common | candidate |
| [video-diffusion-optimization](common/skills/video-diffusion-optimization.json) | common | candidate |
| [vllm-metal](common/skills/vllm-metal.json) | common | candidate |
| [weight-loading-optimization](common/skills/weight-loading-optimization.json) | common | candidate |
