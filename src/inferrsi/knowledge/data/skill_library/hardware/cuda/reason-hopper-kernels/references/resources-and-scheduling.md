# Hopper resource, layout and scheduling tradeoffs

Use this reference after the [synchronization proof](synchronization.md).
**DG**, **C2139**, **PTX87** and **HTG128** are defined in [sources](sources.md).
Source inspection supports mechanisms and constraints; the choices below are
**proposed hypotheses**, not measured tuning advice.

## Budget the whole live set

Hopper WGMMA outputs occupy register fragments. For a single logical `m64n256`
FP32 output distributed over a 128-thread warpgroup, the element-count lower
bound is `64 * 256 / 128 = 128` accumulator values per thread. This arithmetic
excludes other accumulator sets, A fragments in RS forms, scales, addresses,
loop/scheduler state and epilogue temporaries. It does not derive CTA residency.
Count all warpgroups, all roles and compiler allocation granularity; inspect the
compiled register allocation and spills. Do not equate one warpgroup with one
CTA or infer occupancy solely from registers per thread.

For shared memory, use the actual padded layout sizes:

`input stages * (A + B + scale storage per stage) + barriers + descriptors + epilogue scratch + alignment padding`

Check any deliberately overlaid allocations by lifetime before subtracting them.
DG stores output scratch, per-stage operands, per-stage A/B scale tiles and
barriers in one allocation; it rounds B-scale storage for alignment. A payload
byte count is insufficient to calculate resource fit.

| Proposed change | Mechanism and preconditions | Counter-signal / next observation |
| --- | --- | --- |
| Add an input stage | More independent load/compute work can cover an exposed load latency in a sufficiently long loop. Producer and consumer must agree on stage/phase and release. | More SMEM can reduce residency or force smaller tiles; short loops pay fill/drain cost. Compare wait locations, compiled allocation and complete-loop time. |
| Increase tile M/N | More reuse and useful MMA work per loaded tile, if there is enough workload and layout support. | More accumulator/epilogue state and fewer independent tiles can cause spills or underfill. Check useful-versus-padded work and tail dimensions. |
| Reduce tile K or unroll | May shorten live ranges or free SMEM/registers. | More transactions, barriers, instruction/address work and scale boundaries can erase the benefit. Count these costs rather than assuming higher occupancy wins. |
| Redistribute registers by role | A TMA producer may need fewer registers than a math warpgroup. DG calls `warpgroup_reg_dealloc` on its producer group and `warpgroup_reg_alloc` on math groups. | Donation/allocation must obey PTX warpgroup participation and CTA register-pool availability; an increase can wait for registers. Reproduce the role accounting on the actual stack. DG's numeric register budgets are source-specific, not defaults. |
| Cap registers globally | Can change residency if registers are the binding resource. | Compiler spills/recomputation or weaker unrolling may dominate. Use compiled resources and local-memory traffic; do not adopt a Blackwell GEMV contest cap as a Hopper GEMM rule. |
| Overlap epilogue with another tile | Independent warpgroup/output ownership can expose work beyond one tile's epilogue; C2139 contains an SM90 ping-pong kernel with two consumer roles, order barriers and store-drain obligations. | Extra live accumulator and output scratch states consume resources. Prove each store's completion before reusing its SMEM and compare against the simpler schedule. |

HTG128 identifies H100 SM limits and cluster occupancy APIs; use the queried
actual device and kernel limits when designing a launch. Per-SM capacity differs
from per-block usable capacity. Clusters change simultaneous residency; do not
substitute ordinary CTA occupancy for active-cluster occupancy.

## Couple the copy and MMA layouts

A TMA tensor map, shared allocation, swizzle, stage stride and WGMMA descriptor
must describe the same bytes. Include datatype size, contiguous dimension,
strides, base alignment, tile box and tail behavior. For RS forms also check A's
register-fragment mapping. Correct logical matrix indices alone do not prove a
correct physical layout.

**Inspected C2139:** its SS mainloop asserts that both operands are shared-memory
descriptor iterators, that layout atoms divide the tile and that scale
granularities divide the appropriate dimensions; its TMA eligibility check
rejects invalid alignment. **Inspected DG:** separate A/B swizzle parameters,
shared-buffer alignment, SM90 descriptor construction and scale indexing are
part of one path. These are implementation-specific constraints.

**Proposed layout check:** trace one small non-symmetric tile, both operand
majors, stage wraparound and a tail. Follow physical addresses from the tensor
map through SMEM to the selected atom and back through the output mapping.
Choose a supported layout atom/descriptor pair instead of imposing a universal
64-byte or 128-byte swizzle. A bank-conflict observation can motivate a layout
change; it cannot make an illegal descriptor correct.

For ordinary global loads, vectorization requires both per-thread alignment and
a supported instruction width/type. Verify emitted code and transactions.
`technique-vectorized-loads` advertises SM90 while discussing 256-bit Blackwell
loads; the source-page summary of SGLang PR-19794 reports a pre-Blackwell guard.
PTX87's ordinary `ld` vector forms and the selected compiler path must govern a
Hopper implementation. Wider aggregate C++ objects need not become one native
instruction. Cache admission/eviction hints need an observed reuse pattern;
streaming past a cache and retaining hot data are competing choices.

## Separate scheduling problems

A small grid, resource-limited residency, irregular per-tile work and cache
misses can all yield low utilization, with different remedies. Count output
tiles after masking/grouping and padding, active CTAs or clusters, K-iterations,
and their distribution across experts. Use a time trace when available; a
single utilization percentage cannot distinguish these mechanisms.

**Inspected DG:** its SM90 kernel repeatedly requests work from a software
scheduler, and the scheduler maps a persistent block index into grouped/swizzled
coordinates. This establishes a Hopper software-persistence example without
CLC. It does not prove all layouts or grouped modes enter this particular
`1d1d` kernel; its own static assertions allow only Normal and
KGroupedContiguous.

**Proposed comparisons:**

- Compare linear and blocked/swizzled tile order when nearby tiles reuse one
  operand in L2. Confirm the chosen order preserves complete unique output
  ownership and multicast compatibility. A larger locality group may exceed
  the useful cache working set or worsen balance; no order is universally best.
- Consider a software persistent loop when amortized setup or coordinated tile
  ownership is useful. Preserve cross-tile pipeline state and store-drain
  boundaries. Equal-cost tiles still have a final partial-work problem;
  persistence alone cannot eliminate mathematical underfill.
- For thin or irregular grouped GEMM, compare useful work, padding, per-group
  metadata/setup and launch reduction. Empty/tiny groups can dominate scheduler
  overhead. Masked, contiguous-M, pointer-array and K-grouped layouts have
  different indexing and output/reduction semantics.
- Consider split-K/Stream-K only for a demonstrated parallelism deficit and a
  sufficiently long reduction. Include workspace, extra reads/writes, reduction
  or atomic cost, initialization and changed floating-point order. The source
  summary of SGLang PR-16014 reports a Hopper small-batch regression motivating
  `split_k=1`; this is a counterexample to unconditional splitting, not a default
  for this skill.

## Upstream claims deliberately not inherited

KW `pipeline-stages` calls pipelining always beneficial but also acknowledges
short-K overhead and SMEM constraints. Its pattern page calls pipelining wasted
on memory-bound kernels. Retain the conditional resource/dependency analysis,
not either universal statement or a fixed stage count.

KW `register-to-tmem` gives broad register/occupancy estimates and says
register accumulators make epilogue/MMA overlap impossible. The
`double-buffering` page describes Hopper accumulator buffering, and C2139's
SM90 ping-pong kernel supplies a concrete counter-signal. Register accumulators
make overlap costly; they do not establish an architecture-wide impossibility.
Do not import the pages' maximum practical tile size or occupancy arithmetic.

KW `ping-pong-scheduling` is an SM100/FA4 example and says it is not useful on
Hopper. That does not rule out a different Hopper ping-pong schedule. Likewise,
KW's CLC recommendations, TMEM double-buffering, hardware block-scale MMA,
two-SM tcgen05 and software-exp results are excluded from Hopper recipes.
