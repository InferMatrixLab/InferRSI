# InferRSI skill discovery index

Generated metadata for every root `skills/` entry. The source procedures,
references and cases remain authoritative in the checkout; their bodies
are not redistributed by this index. The reference and searchspace matrices
remain the maintained knowledge views. Do not edit generated files by hand.

Index status `imported` and `locally_verified: false` describe these discovery
records. Original status, provenance, license declarations and limitations
are preserved under `skill_metadata`; absent fields remain absent. Unknown
licenses remain unknown. Indexing grants no execution permission or validation.

These are knowledge abstracts (`--kind knowledge`), with namespaced package
IDs distinct from their `checkout_ref` skills. `common` and `skills.discovery`
describe the index, not hardware or task applicability.

Source snapshot: [ac70272978965f0043dcc2ead81afb813c69f63c](https://github.com/InferMatrixLab/InferRSI/tree/ac70272978965f0043dcc2ead81afb813c69f63c/skills).

```bash
inferrsi knowledge search 'profiling' --repo-type inferrsi --limit 50
inferrsi collect --repo-type inferrsi --kind knowledge --limit 50 --material
```

After committing changes to skill headers or sidecars, regenerate from a
development installation with the skills extra. The source revision must
contain the current input paths and bytes (Git checkout filters are respected).
`source_files` hashes identify the canonical Git bytes, not a validation result.

```bash
python tools/build_skill_index.py --source-revision <committed-source-revision>
python tools/build_skill_index.py --source-revision ac70272978965f0043dcc2ead81afb813c69f63c --check
```

`--check` detects missing, stale and unexpected generated records without writing.
References and cases remain source links; they are not separate packaged entries.

| Skill | Original declared status |
| --- | --- |
| [ascend-aclgraph-capture-replay](common/skills/ascend-aclgraph-capture-replay.json) | candidate |
| [ascend-device-health](common/skills/ascend-device-health.json) | candidate |
| [ascend-distributed-parallel](common/skills/ascend-distributed-parallel.json) | candidate |
| [ascend-graph-mode](common/skills/ascend-graph-mode.json) | candidate |
| [ascend-model-adaptation](common/skills/ascend-model-adaptation.json) | candidate |
| [ascend-operator-profiling](common/skills/ascend-operator-profiling.json) | candidate |
| [ascend-operator-tuning](common/skills/ascend-operator-tuning.json) | candidate |
| [ascend-optimization-casebook](common/skills/ascend-optimization-casebook.json) | candidate |
| [ascend-performance-analysis](common/skills/ascend-performance-analysis.json) | candidate |
| [ascendc-tiling-design](common/skills/ascendc-tiling-design.json) | candidate |
| [assess-serving-preemption](common/skills/assess-serving-preemption.json) | candidate |
| [assess-split-backward-schedule](common/skills/assess-split-backward-schedule.json) | candidate |
| [audit-vllm-kv-lifetimes](common/skills/audit-vllm-kv-lifetimes.json) | candidate |
| [calibrate-serving-simulation](common/skills/calibrate-serving-simulation.json) | candidate |
| [cann-attribution-overlap](common/skills/cann-attribution-overlap.json) | candidate |
| [cgroup-resource-controls](common/skills/cgroup-resource-controls.json) | candidate |
| [checkpoint-recovery-consistency](common/skills/checkpoint-recovery-consistency.json) | candidate |
| [choose-parallel-training-plan](common/skills/choose-parallel-training-plan.json) | candidate |
| [cite-check-downstream-pr](common/skills/cite-check-downstream-pr.json) | unspecified |
| [claim-contract](common/skills/claim-contract.json) | unspecified |
| [competitor-scan](common/skills/competitor-scan.json) | unspecified |
| [dcp-async-save-performance](common/skills/dcp-async-save-performance.json) | candidate |
| [dense-performance-evidence](common/skills/dense-performance-evidence.json) | candidate |
| [diagnose-attention-bottlenecks](common/skills/diagnose-attention-bottlenecks.json) | candidate |
| [diagnose-vllm-admission-pressure](common/skills/diagnose-vllm-admission-pressure.json) | candidate |
| [draft-acceptance-issue](common/skills/draft-acceptance-issue.json) | unspecified |
| [evaluate-elastic-serving-placement](common/skills/evaluate-elastic-serving-placement.json) | candidate |
| [host-memory-management](common/skills/host-memory-management.json) | candidate |
| [host-overhead-optimization](common/skills/host-overhead-optimization.json) | candidate |
| [host-overhead-profiling](common/skills/host-overhead-profiling.json) | candidate |
| [inference-benchmark-design](common/skills/inference-benchmark-design.json) | candidate |
| [inference-optimization-casebook](common/skills/inference-optimization-casebook.json) | candidate |
| [kernel-writing-guide](common/skills/kernel-writing-guide.json) | candidate |
| [kv-tier-management](common/skills/kv-tier-management.json) | candidate |
| [npu-skill-factory](common/skills/npu-skill-factory.json) | candidate |
| [optimization-search-policy](common/skills/optimization-search-policy.json) | candidate |
| [os-process-placement](common/skills/os-process-placement.json) | candidate |
| [performance-ceiling-analysis](common/skills/performance-ceiling-analysis.json) | candidate |
| [plan-activation-residency](common/skills/plan-activation-residency.json) | candidate |
| [repository-evolution-analysis](common/skills/repository-evolution-analysis.json) | candidate |
| [rsi-evidence](common/skills/rsi-evidence.json) | unspecified |
| [skill-evolution-playbook](common/skills/skill-evolution-playbook.json) | candidate |
| [storage-io-measurement](common/skills/storage-io-measurement.json) | candidate |
| [torchnpu-device-memory-lifecycle](common/skills/torchnpu-device-memory-lifecycle.json) | candidate |
| [torchnpu-pinned-host-memory-lifecycle](common/skills/torchnpu-pinned-host-memory-lifecycle.json) | candidate |
| [training-input-pipeline](common/skills/training-input-pipeline.json) | candidate |
| [training-resource-budget](common/skills/training-resource-budget.json) | candidate |
| [weight-loading-optimization](common/skills/weight-loading-optimization.json) | candidate |
