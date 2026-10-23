# Case D-C1: Fewer HBM transfers can win despite more FLOPs, then plateau

Status: candidate; empirical_validation: not_run. This is an author-reported paper case, not a reproduced result.

## F: observation and denominator

[D1 Figure 2, p. 6](https://arxiv.org/pdf/2205.14135v2#page=6) compares standard attention with FlashAttention on A100, batch 64, 16 heads, sequence length 1024 and head dimension 64. The boundary is attention forward plus backward, not a model training step:

| Quantity | Standard attention | FlashAttention |
|---|---:|---:|
| Arithmetic | 66.6 GFLOPs | 75.2 GFLOPs |
| HBM read/write volume | 40.3 GB | 4.4 GB |
| Runtime | 41.7 ms | 7.3 ms |

The figure does not restate dtype, repetition policy or precise standard-baseline implementation. Do not silently import those from another experiment. Its middle panel, on the same stated workload but **forward only**, shows reduced HBM traffic as the block size increases and a runtime plateau beyond 256. The paper attributes the plateau to other costs, such as arithmetic, and notes that SRAM bounds tile growth.

## F: counterexample against a stronger short-sequence baseline

[D1 Appendix E.4, Table 7, p. 28](https://arxiv.org/pdf/2205.14135v2#page=28) uses A100-SXM4-40GB, batch 64, 16 heads, d=64, masking and dropout. At sequence length 128:

- Apex FMHA forward 0.10 ms; FA forward 0.08 ms
- Apex FMHA backward 0.17 ms; FA backward 0.20 ms
- Apex FMHA combined 0.27 ms; FA combined 0.28 ms

At length 512, combined times are 2.95 versus 2.81 ms. Those are separately reported combined measurements, not a requirement that separately timed passes add exactly. The source explains that recomputation makes FA backward slightly slower in this short-length comparison. The standard-attention Figure 2 gain must not be applied to the Apex baseline.

## P: proposed decision

When a tiled fused kernel reduces HBM traffic, first verify that the saved transfers explain the measured boundary. Track extra recompute, live fast-memory state and normalization. If larger tiles continue reducing bytes but stop reducing time, reclassify the bottleneck rather than pursuing maximum tile size.

Reject the claim “linear auxiliary memory guarantees a faster kernel.” The formal result is linear **additional** storage plus Θ(N²d²/M) HBM access; for fixed M and d this is not subquadratic in N. Preserve dropout replay and backward correctness before any timing comparison.

Incremental value over prior roofline/evidence skills: a concrete transfer-versus-recompute case, its tile-size stopping condition, and an author-reported stronger-baseline reversal. See [F1–F2](../../mechanisms.md).
