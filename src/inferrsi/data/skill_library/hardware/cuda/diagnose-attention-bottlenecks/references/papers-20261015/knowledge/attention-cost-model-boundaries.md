# Knowledge: attention cost-model boundaries

Status: candidate; empirical_validation: not_run. `F` records paper-established definitions; `P` is the extracted reasoning rule. [Readsets](../../sources.md) and [mechanisms](../../mechanisms.md) provide exact locators.

## F: keep distinct quantities distinct

1. **Auxiliary capacity:** D1 needs O(N) additional statistics beyond Q/K/V/O, not O(N) total bytes independent of d/batch/heads. Total allocation and traffic have different dimensions.
2. **Device IO:** D1's Θ(N²d²/M) counts HBM accesses under its two-level model. Increasing fast-memory capacity or reducing d changes the trade; fixed d and M retain quadratic N dependence. M must use consistent element/byte units. The lower bound is not universal pointwise optimality.
3. **Useful arithmetic and recomputation:** two main forward matmuls versus five backward matmuls in the FA2/FA3 kernel-throughput convention. Excluding or including recomputation changes the reported FLOP denominator.
4. **Operation-class ceilings:** Tensor Core matmul throughput, scalar FP32 and exp/special-function throughput differ. IO improvement can expose non-matmul work without changing the mathematical attention operation.
5. **Parallelism and residency:** enough independent work is not identical to maximum resident occupancy. Tile dimensions, registers, SMEM and shared-gradient contention can all limit useful execution.
6. **Asynchrony and memory:** independent execution resources do not remove data dependencies. Pipeline stages require bounded slots, completion signals and additional live values.
7. **Precision and semantics:** FP8 support does not establish legal operand layouts, negligible conversions or acceptable error. Orthogonal preprocessing preserves QK algebra before quantization; quantization changes the numerical problem.

## P: diagnostic cost sketch, not a fitted model

A conditional bottleneck-time sketch separates transferred HBM bytes / sustainable HBM bandwidth, matmul work / sustained matmul rate, scalar/special-function work / corresponding rate, and exposed synchronization/issue/communication costs. Measured attainable rates produce empirical, condition-dependent estimates, not certified physical lower bounds. A true lower bound requires justified upper limits for the rates and assumptions establishing compulsory work/traffic; keep these separate from measured rates. The estimated component times do not generally add, because some can overlap, and their maximum is not necessarily achievable, because of dependency and resource constraints. The papers motivate this decomposition; they do not supply a universally calibrated predictor for another device or workload.

Reclassify the bottleneck after each change. “Less IO” is a local improvement in one term. “More occupancy” can increase traffic or reductions. “More stages” can force smaller tiles. “FP8” can expose unchanged exp throughput and additional format/layout work. Evidence must identify the currently exposed term.

## F/P: portability boundary

| Transferable reasoning | Concrete paper instantiation, not a portability guarantee |
|---|---|
| Carry online sufficient statistics and avoid full intermediates | CUDA fused attention, GPU HBM/SMEM hierarchy |
| Assign disjoint finished outputs where possible | Warps/CTAs, split-Q, shared-memory reductions and dQ atomics |
| Match producer/consumer ownership to asynchronous units | Hopper TMA, WGMMA, setmaxnreg, bar.sync |
| Bound live pipeline state and verify realized overlap | NVIDIA register budgets, NVCC/SASS scheduling |
| Account for legal layouts and transforms | FP8 WGMMA k-major restriction, LDSM/STSM, register byte permutations |
| Validate error against the appropriate precision baseline | e4m3, block scales, random-sign/Hadamard processing in D3 |

P: a future hardware port needs evidence for analogous local-memory capacity/bandwidth, matrix/vector execution, completion/barrier semantics, legal layouts, compiler scheduling and numerical behavior. This is a future gate, not an NPU result. All memory levels discussed here belong to the **Accelerator** resource domain. Multi-GPU training hardware in an experiment does not establish a communication optimization.

## Metric normalization rules

- Label kernel forward, backward, combined and whole-model training separately; never concatenate their headline speedups into a generation ranking.
- Preserve N, batch, heads, d, mask/dropout, dtype/accumulator, device/power/clocks, baseline version and repetition policy when stated; mark unstated fields unknown.
- D2/D3 kernel counts halve for causal masking; D2's whole-model convention explicitly does not halve its attention term. Model-FLOP utilization and attention-only percentage of peak therefore cannot be interchanged.
- A plot's rounded length label may hide a deliberately changed shape: D3 FP8 Appendix C.2 uses 4224/8448/16896. Exact batch/shape must be established before deriving latency or comparing another plot.
- Accuracy means the stated metric and baseline: D3's synthetic FP64-reference RMSE and its 2.6× FP8-baseline ratio do not establish large-scale training stability or downstream model quality.
