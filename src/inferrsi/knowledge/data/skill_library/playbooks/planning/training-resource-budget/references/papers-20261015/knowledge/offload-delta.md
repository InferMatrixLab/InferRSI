# Incremental extension to training-offload knowledge

Status: candidate; empirical_validation: not_run. F = source fact; P = proposal. Local ownership is training-resource-budget. The supplier's earlier diagnose-training-offload archive is unavailable in this integration; its prior coverage is a carried supplier claim, not a locally imported capability. [Exact ZeRO-Offload v1 evidence](../references/source-readset.md), [ZO1–ZO3 cards](../notes/training-memory-scheduling.md).

## Retain existing coverage

The previous offload notes (prior archive `omnirsi-paper-intelligence-2026-10-15.zip`, semantic path `notes/offload.md`) and source audit (prior archive `omnirsi-paper-intelligence-2026-10-15.zip`, semantic path `notes/references/offload-source-notes.md`) already explain phase memory, slow-tier pipelines, collective reconstruction, tiling, initialization and external/tied parameters. Do not duplicate these as new discoveries.

## P: Proposed additions

- Before choosing tensor offload alone, inspect whether moving the optimizer computation with its FP32 state reduces required traffic. Record CPU/update ownership and avoid redundant per-rank host work. F source: ZO §§3–4.
- Distinguish optimizing CPU update from enabling delayed updates. CPU-Adam vectorization/threading/tile-copy is a system optimization; DPU changes training semantics. F source: ZO §§5.1–5.2 and §6.2.4.
- Include an offload-free fallback when all ranks can fit adequate microbatches. F counterexample: ZeRO-2 surpasses ZeRO-Offload at 64/128 GPUs in the 10B experiment (§6.2.3/Fig. 11).
- Do not carry the Table 1 printed memory figure into a universal byte ledger: its final 4M/8× row conflicts with a 16M baseline. Re-derive actual optimizer/precision/buffer accounting as the existing skill already requires.
- If exact execution is required, leave one-step DPU out. If a user separately accepts changed semantics, propose representative convergence/quality checks; the historical GPT-2/BERT tests do not authorize it.
