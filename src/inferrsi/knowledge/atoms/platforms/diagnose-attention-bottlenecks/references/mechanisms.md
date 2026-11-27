# Mechanism extraction: from HBM traffic to execution and precision

`F` is source fact, including author-reported evidence; `P` is a proposed operational rule. Evidence is historical and not locally reproduced. [Source IDs and exact readsets](sources.md) control every claim below.

## F1 / P1. Online sufficient statistics remove the quadratic intermediate

- **Objective:** compute dense softmax attention with lower device-HBM traffic and extra storage, without changing its algebraic definition.
- **Assumptions:** Q, K, V and final O reside in device HBM; fast memory is much smaller but faster; row-wise softmax can be accumulated from blocks using a running maximum and normalizer. N is sequence length, d head dimension, M fast-memory capacity.
- **Variables/constraints:** query/key tile sizes Br/Bc; Q/output and K/V tiles, score tile and statistics must fit in fast memory. D1's asymptotic constraints include Br*d = O(M), Bc*d = O(M), Br*Bc = O(M). Capacity units must match element counts; actual mixed dtypes require a byte budget.
- **Mechanism:** compute each score tile locally, update stable row maximum/normalizer and weighted output, and never materialize the complete N-by-N score or probability matrix in HBM. D1 Algorithm 1 has key/value blocks outside query blocks; D2 subsequently changes forward ownership/order.
- **Benefit/cost:** D1 Theorem 1 gives O(N²d) arithmetic and O(N) extra memory beyond inputs/output. Saved full intermediates are replaced by repeated tiled input/output traffic and normalization work. Linear extra storage is not linear execution time or zero HBM IO.
- **Evidence:** D1 §3.1–3.2, Algorithm 1, Theorems 1–2 and Appendix C. The standard materializing algorithm incurs Θ(Nd+N²) HBM accesses; its tiled counterpart incurs Θ(N²d²/M) for d ≤ M ≤ Nd.
- **Limits/counter-signals:** fixed M and d leave quadratic N dependence. Proposition 3's lower-bound quantifier is “no uniform asymptotic improvement for all M,” not pointwise optimality. A smaller allocation alone does not establish fewer transfers, lower latency or enough schedulable work.
- **P1 rule:** identify the materialized tensor and transfer count before proposing tiling. Use the fast-memory fit conditions and preserved softmax invariant; do not promise a complexity class or speedup from a lower allocation counter.

## F2 / P2. Recomputation can buy speed, but the exchange can reverse

- **Objective:** avoid writing/storing full forward intermediates solely for backward.
- **Assumptions:** blocks can be recomputed from inputs and saved statistics; backward needs the same dropout decisions as forward; transfer cost can exceed the added compute cost.
- **Variables/constraints:** saved O and row statistics; RNG state; repeated Q/K loads; recomputed score/probability blocks; fast-memory budget for more simultaneous backward values. D1 Appendix B derives D_i = dO_i dot O_i, avoiding a full attention-row reduction.
- **Mechanism:** regenerate S/P inside fast memory; reconstruct dropout from saved RNG state; accumulate gradients by blocks. D1 Algorithms 2–4 explicitly preserve the forward state required by backward.
- **Benefit/cost:** fewer HBM reads/writes and linear auxiliary state at the cost of extra matmul/scalar work and stricter replay correctness. This is selective recomputation, not a claim that all checkpointing is faster.
- **Evidence:** D1 Figure 2, A100, batch 64, 16 heads, N=1024, d=64, forward+backward: standard 66.6 GFLOPs / 40.3 GB HBM R/W / 41.7 ms; FA 75.2 / 4.4 / 7.3. These are that figure's measurements, not the different Appendix E.6 workload. Figure 2 middle shows forward latency flattening beyond block size 256 despite further IO reduction.
- **Limits/counter-signals:** Table 7's stronger short-sequence Apex FMHA baseline reverses part of the trade: on A100-SXM4-40GB, batch 64, 16 heads, d=64, with masking and dropout, at N=128 FA backward is 0.20 versus 0.17 ms and combined 0.28 versus 0.27 ms. Larger d or smaller SRAM requires smaller tiles (Appendix E.5); larger tiles can exceed capacity or expose arithmetic bottlenecks.
- **P2 rule:** compare avoided traffic with newly exposed recompute and normalization, separately for forward/backward. Stop enlarging tiles when transfer reductions no longer reduce latency or resource pressure rises.

## F3 / P3. FLOPs of different types are not interchangeable

- **Objective:** raise useful matmul utilization after HBM-intermediate traffic is reduced.
- **Assumptions:** the device accelerates matmul far more than scalar operations. D2 §3.1 quotes A100 theoretical rates of 312 TFLOP/s FP16/BF16 matmul and 19.5 TFLOP/s non-matmul FP32.
- **Variables/constraints:** number of per-tile rescalings/divisions; running output, maximum and exponential sum; stored backward statistic; actual operation-specific throughput. The quoted 16:1 ratio compares these hardware paths, not all FLOPs or measured instruction latencies.
- **Mechanism:** maintain an unnormalized running weighted output through the key-block loop; normalize once at the end. Save row logsumexp rather than separate maximum and exponential sum for backward. Maintain stable max-shift rescaling when the maximum changes.
- **Benefit/cost:** fewer non-matmul operations and a simpler saved statistic, while preserving dense exact-attention algebra. Correct rescaling remains required; do not eliminate it as “overhead.”
- **Evidence:** D2 §3.1, Algorithms 1–2. Its §4 measures the combined FA2 redesign, not a standalone percentage attributable only to scalar-work reduction.
- **Limits/counter-signals:** D2 v1 has displayed rescaling/wording inconsistencies recorded in sources.md. Historical throughput ratios do not replace a current device's scalar, special-function and matmul ceilings.
- **P3 rule:** after IO fusion, count/observe scalar and special-function work separately; propose algebraic work removal only with a correctness invariant and an isolated test plan.

## F4 / P4. Expose independent sequence work without hiding reduction cost

- **Objective:** use more of the GPU when batch times heads yields too few independent workers.
- **Assumptions:** query rows can be computed independently in forward; backward partitions share some gradients. Batch, heads and sequence shape control the available work; SM count and per-CTA resources control execution.
- **Variables/constraints:** batch*heads, number of query/key tiles, CTAs, resource occupancy, and dQ reduction/atomic contention. D2's “say ≥80” blocks observation is an A100-context heuristic, not a cross-device threshold.
- **Mechanism:** D2 forward puts a query row block in each worker, with the key/value-block loop inside; different forward workers need not communicate to form their output. Backward assigns key-column blocks and atomically accumulates shared dQ. D2 credits the loop swap and sequence parallelism to Phil Tillet's Triton implementation; that code was not read here.
- **Benefit/cost:** more independent work in small-batch/long-sequence regimes; additional reduction/atomic work in backward. The paper's “occupancy” discussion is resource use and parallelism, not proof from a specific achieved-occupancy hardware counter.
- **Evidence:** D2 §3.2 and Figure 2, with combined experimental support in Figures 4–7 and Table 1.
- **Limits/counter-signals:** if sufficient work already exists, partitioning need not be the remaining bottleneck. In backward, independence of dK/dV does not imply independence of dQ. Current causal scheduling/load balance is not audited.
- **P4 rule:** count available independent tiles and identify shared outputs before changing parallelism. Keep forward and backward ownership/reduction plans separate.

## F5 / P5. Partition by finished outputs to remove unnecessary shared-memory reductions

- **Objective:** reduce inter-warp traffic/synchronization inside a CTA.
- **Assumptions:** an owner can produce a disjoint output slice while sharing read-only operands; the chosen matrix instruction layout permits it.
- **Variables/constraints:** split-Q versus split-K; warps per CTA (paper commonly 4 or 8); tile geometry; registers and shared memory. D2 commonly uses {64,128} by {64,128} tiles, manually selected by d and device memory.
- **Mechanism:** D2 §3.3 contrasts FA's split K/V partial outputs, which must be written, synchronized and reduced, with query-row ownership: each warp consumes common K/V and finishes its output slice. This removes that inter-warp output reduction in forward. Backward still needs synchronization.
- **Benefit/cost:** less shared-memory communication; larger tiles further reduce loads/stores but increase resource demand, with spills or failure to fit past a limit.
- **Evidence:** D2 §3.3 and Figure 3; overall benchmark gains in §4. No separately measured split-Q-only speedup is provided in this pin.
- **Limits/counter-signals:** “no inter-warp output reduction” is narrower than “no synchronization.” Copying a tile/warp count without head-dimension/resource context can worsen performance.
- **P5 rule:** assign ownership of complete outputs where feasible, then check resource use and actual shared-memory traffic. Do not attribute all FA2 gains to work partitioning alone.

## F6 / P6. Asynchronous producers and consumers expose a second scheduling layer

- **Objective:** hide data-movement/issue latency and overlap lower-throughput softmax with matmul.
- **Assumptions:** copies and matmul can progress asynchronously with independent execution units, with explicit completion semantics. D3 uses Hopper TMA/WGMMA and dynamic register redistribution.
- **Variables/constraints:** s-stage circular shared-memory buffer, producer/consumer warp allocation, register allocation and ownership of each buffer stage. The SMEM buffer depth is not automatically the GEMM-softmax pipeline depth.
- **Mechanism:** producers wait for a free slot, issue Q/K/V loads and notify consumers after completion; consumers wait for data, compute and release slots only when consumption ends (Algorithm 1). Inter-consumer pingpong scheduling uses barriers so one warpgroup's softmax overlaps another's GEMMs. Backward adds a dQ-writer role to decouple contended accumulation from consumers (Appendix B.1).
- **Benefit/cost:** better overlap and a larger register share for compute consumers; costs include synchronization, buffers, more roles and contention that still exists. D3 §3.1 quotes 989 TFLOP/s FP16 matmul versus about 3.9 trillion special-function operations/s on its H100; exp becomes relatively more important when FP8 doubles matmul throughput.
- **Evidence:** D3 §3.1, Figure 1 and Algorithms 1/3. Its pingpong example reports 570 to 620–640 TFLOP/s for FP16 forward, d=128 and N=8192; the paragraph does not fully specify batch/heads, so it is qualitative supporting evidence, not a fully matched case. Table 2 supplies a better specified component ablation.
- **Limits/counter-signals:** ideal pingpong diagrams are not exact realized schedules. Dedicated async primitives and barrier semantics are Hopper-specific here. dQ-writer specialization does not eliminate accumulation traffic or prove determinism.
- **P6 rule:** state dependency, completion and buffer-reuse contracts before proposing overlap. Budget resources and inspect actual exposed stalls; do not delete waits to create apparent overlap.

## F7 / P7. Pipeline across iterations, then charge register and compiler costs

- **Objective:** overlap softmax with matmul despite within-iteration dependencies QK→softmax→PV.
- **Assumptions:** independent work from different iterations can coexist; intermediate state survives until its consumers finish; the compiled schedule overlaps the intended units.
- **Variables/constraints:** pipeline depth, tile sizes, S_next register buffer, outstanding GEMMs and waits. D3's two-stage scheme adds Br*Bc*sizeof(float) register storage per threadblock; its three-stage extension adds still more P/scaling state.
- **Mechanism:** issue future QK and earlier PV asynchronously, wait only when their results are required, and perform softmax on ready scores while other GEMM work progresses. Algorithm 2 describes the consumer replacement; Appendix B.2 inspects the author's simplified SASS.
- **Benefit/cost:** more useful overlap; extra live state, smaller feasible tiles, spill risk and compiler-order sensitivity. The source-level diagram alone is insufficient evidence.
- **Evidence:** D3 Table 2, non-causal FP16, {batch,N,heads,d}={4,8448,16,128}: full FA3 3.538 ms / 661 TFLOP/s; no GEMM-softmax pipeline with warp specialization 4.021 ms / 582; pipeline without warp specialization 4.105 ms / 570. Appendix B.2 observes some overlap, but the second WGMMA is not interleaved.
- **Limits/counter-signals:** Appendix B.3 says three-stage is worse: the compiler does not realize the hoped-for second-GEMM overlap and register demand forces smaller tiles. No numerical three-stage timing is supplied there. Table 2 does not include a neither-feature baseline and does not establish additive independent gains.
- **P7 rule:** choose pipeline depth jointly with tile/resource constraints and verify generated scheduling. A deeper pipeline that cannot add overlap or loses tile efficiency should be rejected.

## F8 / P8. Low precision requires layout work as well as faster arithmetic

- **Objective:** exploit FP8 matmul throughput without paying away the gain in layout conversions.
- **Assumptions:** Hopper FP8 WGMMA accepts k-major operands, unlike the more flexible FP16 input layouts; attention chains two GEMMs with intermediate FP32 accumulators.
- **Variables/constraints:** V orientation, FP32 accumulator versus FP8 operand-A register layout, shared-memory transpose, byte permutations and dtype conversion.
- **Mechanism:** D3 §3.3 loads V tiles and transposes them in-kernel with LDSM/STSM plus register movements. Producer work can overlap preceding/current GEMMs. It permutes the intermediate P layout and matches V's row permutation so the product remains consistent, avoiding cross-thread ownership shuffles in this design.
- **Benefit/cost:** avoids a standalone global-memory transpose and enables FP8 GEMMs; adds on-chip layout work and ties the implementation to instruction layout. A fused preceding-operation alternative can be hard to integrate in a general library.
- **Evidence:** D3 §2.2/§3.3, Figures 3–4, Figure 7 and Appendix C.2 Figure 9. Appendix C.1 fixes H100 SXM5 80GB, 700W, 1830MHz and historical library versions.
- **Limits/counter-signals:** FP8 FA3 is not uniformly best against cuDNN. At d=256, causal, the largest plotted FP8 length has FA3 1024 versus cuDNN 1099 TFLOP/s. That “16k” axis means N=16896 in Appendix C.2. Footnote 10 says FP16 FA3 has a persistent kernel/load-balancing strategy and FP8 does not, affecting small-N/causal comparisons.
- **P8 rule:** include transpose, quantization and conversions inside the relevant measurement boundary. Do not claim that FP8 doubles attention speed or that its layout recipe is portable merely because another device supports FP8.

## F9 / P9. Quantization error needs its own evidence and ablation

- **Objective:** reduce FP8 error with outlier activations/features.
- **Assumptions:** Q/K share an orthogonal transform M, preserving (QM)(KM)^T=QK^T in exact arithmetic; quantization follows the transform. Matmul/softmax intermediate precisions and scaling are explicit.
- **Variables/constraints:** block scale sizes Br*d or Bc*d, e4m3 FP8, per-tensor baseline, outlier distribution, transform cost, output error and downstream quality.
- **Mechanism:** quantize Q/K/V per tile; mix Q/K using random sign diagonal and Hadamard factors before quantization to spread outliers. Fast Hadamard processing costs O(d log d) instead of a dense O(d²) transform. D3 proposes fusion with a preceding memory-bound operation; this is not an unconditional zero-cost operation.
- **Benefit/cost:** improved local quantization error, with scaling/transform work and a new numerical contract. The attention output is not generally identical after quantization even though the unquantized orthogonal transform is invariant.
- **Evidence:** D3 §4.3/Table 3 uses FP64 reference and synthetic entries N(0,1)+N(0,100)*Bernoulli(0.001); the second normal has standard deviation 10. FP8 baseline uses per-tensor scaling, FP32 matmul accumulation and FP16 softmax intermediate. RMSE: baseline FP8 2.4e-2; full FA3 FP8 9.1e-3; without block quantization 9.3e-3; without incoherent processing 2.4e-2. FP16 baseline 3.2e-4 versus FA2/FA3 1.9e-4 each.
- **Limits/counter-signals:** about 2.6× lower RMSE is relative to that FP8 baseline, not relative to FP16, and is not a model-quality gain. The ablation suggests the orthogonal processing supplies most of the improvement in this synthetic setting; it does not show block scales are useless on other data. Shape/repetition details for this accuracy test are not established by the inspected §4.3 text. §5 leaves large-scale low-precision training effects open.
- **P9 rule:** test accuracy separately from speed on representative outlier distributions and the user's model-quality target. Retain a higher-precision reference and per-component ablations; reject headline accuracy ratios without their baseline and metric.
