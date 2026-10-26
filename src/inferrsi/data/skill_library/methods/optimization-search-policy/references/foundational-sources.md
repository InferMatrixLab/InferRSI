# Foundational source inventory and notices

Scope: issue #131 knowledge consolidation. Inspected 2026-10-26; no engines,
models or GPU experiments executed. Authored summaries retain attribution and
source versions; no upstream paper, figure, code or documentation is redistributed.
Upstream rights remain with their authors/publishers. Public availability does
not grant a software license. Unknown reuse rights remain UNKNOWN; the repository
license for this authored synthesis does not relicense cited sources.

## Inventory before extraction

- `assess-serving-preemption` already owns Orca O1–O4 and FastServe, including
  source-reported low-load and kernel counter-results. Reuse its
  [readset](../../assess-serving-preemption/references/source-notes.md), without
  claiming a fresh paper reread or a new mechanism.
- `case.admission-drain-occupancy` already owns the finite-cohort diagnostic and
  frozen evidence pointers. Reuse that ID and its INCONCLUSIVE boundary.
- `diagnose-vllm-admission-pressure`, `audit-vllm-kv-lifetimes`,
  `kv-tier-management` and `audit-afd-p2p-exchanges` own engine-specific procedures.
  Their retained source revisions are independent of these paper/document versions.
- `choose-parallel-training-plan` already owns Alpa stage/mesh/sharding guidance;
  it remains training-only. No training procedure is relabeled as inference.
- The earlier foundation archive was absent from the packaged library. Historical
  Sarathi/DistServe/PagedAttention mentions are leads, not retained case bodies.
  The five new cases below fill missing decision examples; they do not reconstruct
  the unavailable archive or claim its remaining papers were read.

## Newly inspected sources

| Source and immutable edition | Actual readset | Case / evidence boundary | Rights |
| --- | --- | --- | --- |
| Agrawal et al., [Sarathi-Serve](https://www.usenix.org/system/files/osdi24-agrawal.pdf), OSDI 2024 proceedings, pp. 117–134 | §§4.1–4.3; §5.3; §5.4/Fig. 14/Table 4, text and table | `case.sarathi-chunk-budget`; chunk/scheduler interaction and reported prefill overhead, no digitized curves | Authors/USENIX; reuse license UNKNOWN |
| Kwon et al., [PagedAttention](https://arxiv.org/html/2309.06180v1), arXiv 2309.06180v1 | §§4.1–4.5; §§7.1–7.3, text and captions | `case.paged-kv-allocation`; allocation versus kernel/block/transfer costs | See source license; no source material copied |
| Zheng et al., [SGLang](https://arxiv.org/html/2312.07104v2), arXiv 2312.07104v2 | §3; §6.3; Appendix A.4 | `case.prefix-reuse-locality`; reuse/ordering, no-reuse overhead and distributed trade-off | arXiv perpetual non-exclusive license; no redistribution grant inferred |
| [vLLM prefix caching](https://docs.vllm.ai/en/v0.10.2/design/prefix_caching.html), v0.10.2 | Hash identity, cache isolation, data structure, allocation/free/eviction | Same prefix case; V1 identity/isolation supplement, separate from SGLang | Documentation license not independently resolved: UNKNOWN |
| Zhong et al., [DistServe](https://www.usenix.org/system/files/osdi24-zhong-yinmin.pdf), OSDI 2024 proceedings, pp. 193–210 | §§3–4; §6.1; §§6.3–6.4, text/table and ablation description | `case.distserve-phase-placement`; real-system and simulated evidence distinguished | Authors/USENIX; reuse license UNKNOWN |
| NVIDIA, [CUDA C Best Practices Guide](https://docs.nvidia.com/cuda/archive/11.8.0/cuda-c-best-practices-guide/index.html), archived 11.8.0 | §§9.1–9.1.2 | `case.cuda-copy-overlap`; documented prerequisites, no experiment | NVIDIA documentation terms; no code or diagrams copied |

Case JSON uses existing `sources`, `applicability`, `limitations` and validation
fields. Axes, resource layers, signals, invariants, metrics and rollback remain
in the case body rather than a new schema. Local baseline/candidate artifacts
are absent (not_run); imported author reports never become locally verified
through packaging, deterministic retrieval tests or matrix placement.
