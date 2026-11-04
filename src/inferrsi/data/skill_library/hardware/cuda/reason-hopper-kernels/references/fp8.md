# FP8 GEMM: scale, partial-sum and layout contracts

Read this for FP8 errors or a proposal to replace a higher-precision GEMM.
**DG** and **C2139** are the inspected code anchors in [sources](sources.md).
KW's DeepGEMM/FP8/fine-grained-quantization pages supply motivation, with the
contradictions below. Native compilation, accuracy and speed remain **not_run**.

## Identify the actual quantized operation

**Proposed contract:** write the quantized operands, scale interpretation
(multiplier versus inverse), scale datatype and granularity along M/N/K,
physical scale layout/strides/padding, operand majors, accumulator behavior,
epilogue alpha/beta/bias and output datatype. Keep the dequantization reference
and production input distributions. A shape-compatible scale tensor with the
wrong major dimension can return plausible but wrong outputs.

Where scale products vary along K, the conceptual result is a sum of separately
scaled partial dot products:

`C[m,n] = sum_chunks(partial_dot(qA[m,chunk], qB[n,chunk]) * sA[m,chunk] * sB[n,chunk])`

This expresses multiplier scales for an NT-style example; it is not an API or an
instruction sequence. Applying one scale after the entire reduction is valid
only if the relevant scale product is constant over that reduction. Keep
quantization error, partial accumulation error, scale application/rounding and
output conversion separate when diagnosing numerical failures.

## What the selected Hopper code actually establishes

DG's inspected **SM90 1d1d** kernel requires `BLOCK_K == 128`, E4M3 input pointers
and FP32 C/D. It allocates FP32 A scales for each M row and B scales for each N
row per stage, and loads both scale tiles with TMA. This is not direct evidence
that this kernel consumes the 128-by-128 weight-block scale layout described by
KW's general DeepGEMM narrative. Other DeepGEMM variants and dispatchers are
outside this readset.

Its FP8 atom has `M=64`, `K=32` and a selectable N; thus a 128-element K chunk
contains four such WGMMA operations. The first operation starts that partial
accumulator with zero scale-out; following operations accumulate. The kernel
commits and waits, releases the input slot, and combines each partial result
with the row's A/B scales into a separate FP32 final accumulator. Scale values
are read before releasing the slot. This is **inspected source behavior**, not a
universal promotion interval or an accuracy guarantee.

C2139's inspected SM90 block-scaled collective has configurable M/N scale
granularity and `ScalePromotionInterval`, asserts the interval's supported
multiple, and uses `GmmaFP8Accumulation` plus scale application. The associated
example warns that its runtime promotion interval must match the
kernel schedule. These configuration units must be read from that
implementation; they are not interchangeable with DG's K-chunk length.

## Make the precision/performance exchange explicit

| Candidate | Expected mechanism | Counter-signal and next check |
| --- | --- | --- |
| Finer scales | Localize outlier influence to a smaller group. | More scale storage/transfers, quantization and layout work; source motivation does not prove lower model error. Compare outlier-heavy, cancellation-heavy and representative inputs at the required output/quality boundary. |
| More frequent partial promotion | Bound the amount of accumulation performed before software scaling/FP32 accumulation. | Extra CUDA-core work, waits and two live accumulator sets can cost throughput/registers. Confirm units, group completion, tail chunk behavior and matched reference rounding. |
| Change scale major/packing | May remove conversion or suit copy/MMA access. SGLang PR-9559's summary reports K-major scale support avoiding conversions at its own revision. | All producers, descriptors, strides and consumers must agree; metadata-only reinterpretation is unsafe. Include conversion and allocation in the measured boundary. |
| Swap A/B or transpose the problem | Can improve useful tile shape for small M; selected source summaries report SM90 swapAB paths. | Changes output/scale indexing, operand layout and epilogue orientation. Validate non-square and tail cases and include transformations; no small-M universal dispatch rule is imported. |
| Reuse quantized operands/scales | Can amortize preprocessing if the represented tensor and scale policy remain unchanged. | Stale activations, mismatched calibration or changed weights invalidate reuse. Keep the actual caller and lifetime in the later test scope. |

**Proposed stop conditions:** wrong outputs, nonfinite/overflow behavior outside
the agreed contract, unsupported operand/scale layout, a resource overrun/spill
that defeats the objective, or a gain that disappears when quantization,
conversion, promotion, reduction and epilogue work is counted. Operator parity
still does not certify model quality or serving benefit.

## Preserve unresolved source claims

- KW `deepgemm` describes Nc=128 in terms of columns/N in prose and a
  `WGMMA_N` variable, whereas its fine-grained-quantization page describes K
  elements; `fp8-block-scale-gemm` also says 128 WGMMAs in a comment. The
  inspected DG atom/chunk relationship above is the bounded reconciliation.
- KW uses an approximate FP22 label, quotes a bounded relative-error figure and
  calls one promotion cadence necessary. This readset does not establish those
  numerical guarantees. Keep the precise PTX datatype/rounding contract and
  measure error for the actual implementation and input domain.
- KW generalizes activation 1-by-128 and weight 128-by-128 scales, NT-only SM90,
  JIT behavior and grouped layouts across DeepGEMM. The selected `1d1d` source
  validates only its own kernel constraints; dispatcher and other variant
  support remain unmined. Do not infer a library-wide support matrix.
- KW's native UE8M0/tcgen05 descriptions belong to its Blackwell branch. A
  source summary about E8M0 scales on Hopper does not add native block-scaled
  WGMMA. FP4 weight emulation/dequantization paths likewise do not establish
  Hopper hardware NVFP4 MMA support and are outside this recipe.
- H800 throughput/utilization and contest figures in KW remain upstream reports.
  No numerical performance or quality result is imported as local evidence.
