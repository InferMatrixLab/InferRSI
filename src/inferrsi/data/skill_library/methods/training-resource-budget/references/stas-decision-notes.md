# Stas Bekman scoped decision notes

**Attribution:** Stas Bekman, *Machine Learning Engineering Open Book*,
[stas00/ml-engineering](https://github.com/stas00/ml-engineering/tree/ee7517e0f562ff0e7d56c3e88c619d0c0c496ba7),
revision `ee7517e0f562ff0e7d56c3e88c619d0c0c496ba7`.
The source skill explicitly declares **CC BY-SA 4.0**. This file is a shortened,
reorganized, paraphrased adaptation and is distributed under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Retain attribution,
the license link and change indication in downstream adaptations; apply
share-alike to adapted material. This notice does not relicense independent
DeepSpeed/MindSpeed materials or the repository as a whole. No endorsement by
Stas Bekman is implied.

Inspected 2026-10-15. No source commands were executed and no numerical gains
were transferred. These are practitioner decision principles, not local tests.

## Incremental rules and their limits

| Signal or choice | Decision principle | Evidence boundary |
|---|---|---|
| MFU/HFU changed after recomputation or precision changes | Retain the FLOP-count convention, theoretical denominator and timed interval. HFU can count recomputation that MFU excludes. Pair ratios with useful workload throughput. | Different operation counts or forward/backward-only versus full-step timing invalidate direct comparison; mixed precision complicates a single peak denominator. |
| High short-burst matmul result | Separate a transient attainable ceiling from sustained compute under the node's shared power/cooling load. | Maximum-achievable and maximum-sustainable concepts are source methodology; no ceiling benchmark was run here. |
| Slow collective or confusing bandwidth figure | Retain collective kind, payload size, participating ranks and intra-node versus inter-node path. Keep algorithm bandwidth and bus bandwidth distinct. | The benchmark script is only a source entry point, not an audited or executed implementation. Host/device copies and shared-memory IPC do not qualify this network cell. |
| CPU-heavy offload slows a rank | Relate process and memory locality to the actual accelerator/NUMA topology; rank-local CPU work can expose cross-socket cost. | Source notes small effect for CPU-light work. Never copy example CPU IDs or claim universal improvement. No affinity was changed. |
| Intermittent synchronized-step stalls | Correlate per-rank garbage-collection events with collective arrival/step spikes before attributing them to the fabric. | Source proposes scheduled manual collection when automatic collection creates stragglers. That is an experiment lead, not permission to disable collection or proof of cause; track memory if later authorized. |

## Exact readset

- [skills/ml-engineering/SKILL.md](https://github.com/stas00/ml-engineering/blob/ee7517e0f562ff0e7d56c3e88c619d0c0c496ba7/skills/ml-engineering/SKILL.md#L21-L79):
  attribution, bottleneck-first principles, compute/memory/network/NUMA/GC routing.
- [skills/evaluate-cluster/SKILL.md, first 100 lines](https://github.com/stas00/ml-engineering/blob/ee7517e0f562ff0e7d56c3e88c619d0c0c496ba7/skills/evaluate-cluster/SKILL.md#L1-L100):
  compute ceiling and collective-bandwidth definitions only. Ignore its
  instructions to update to latest, install tools or run a cluster campaign.
- [training/performance/README.md, 129–180](https://github.com/stas00/ml-engineering/blob/ee7517e0f562ff0e7d56c3e88c619d0c0c496ba7/training/performance/README.md#L129-L180):
  MFU/HFU and comparison caveats.
- [NUMA, 748–789](https://github.com/stas00/ml-engineering/blob/ee7517e0f562ff0e7d56c3e88c619d0c0c496ba7/training/performance/README.md#L748-L789)
  and [garbage collection, 1030–1047](https://github.com/stas00/ml-engineering/blob/ee7517e0f562ff0e7d56c3e88c619d0c0c496ba7/training/performance/README.md#L1030-L1047).

Source fio, input-pipeline, recovery and other runbook sections were not mined.
No original benchmark script, raw experiment or historical model result was
validated. Concepts transfer only after workload/mode-specific qualification.
