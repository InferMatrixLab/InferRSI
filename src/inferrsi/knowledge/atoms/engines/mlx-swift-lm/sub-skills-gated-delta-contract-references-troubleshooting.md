# Gated-delta troubleshooting

Use the [source contract](recurrence-and-state.md) before changing precision or
branch selection. These are discriminating checks, not permission to install
toolchains, launch training, fetch weights or modify upstream code.

| Signal | Likely boundary | Small check / safe response |
| --- | --- | --- |
| Drift begins at a prompt chunk boundary | State was rounded to input precision | Inspect actual retained-state dtype/bytes before and after boundary; public entry uses FP32, and later upcast cannot recover lost bits |
| Trailing Dk perturbation has no effect | Fused integer Dk/32 partition dropped a tail | Preserve the public modulo guard; Dk=48 must use ops; do not call the lower-level kernel to force it |
| Q/K shapes work but value-head mapping fails | Hv/Hk grouping contract | Check matching B/T, equal Q/K shape and divisible positive head counts; selected model constructors enforce this, raw API does not supply a full validator |
| Backward reports no CustomKernel VJP | Training entered fused kernel | Preserve caller `useKernel: !training`; a temporary fallback at one Dk is not a training policy; actual gradients still require native tests |
| Ops path was called a CPU pass | Algorithm route confused with backend | Record actual MLX device/backend separately; no CPU inference claim follows from `useKernel:false` |
| Mask-false Y differs between paths | Emitted Y versus carried-state masking | Keep source asymmetry explicit; compare both Y and state on actual device and assess whether caller consumes masked positions; do not announce a confirmed model bug |
| Masked call fails although unmasked kernel exists | Public gate and selected variant availability differ | Keep two availability facts; source selects masked object later and may fatalError; do not promise automatic ops fallback |
| Narrowed/transposed input behaves differently | Provider packing/contiguity contract | Preserve actual strides/offsets; inspect matched MLXFast contract and executed bytes; no blanket arbitrary-stride support or diagnosed bug from source pointer indexing alone |
| Tiny Q/K tokens drift despite ordinary magnitudes passing | RMS mean epsilon versus L2 sum epsilon | Preserve epsilon divided by Dk and separate Q/K scaling; use near-epsilon native comparison, not only normal-scale inputs |
| Recurrent dot loses small terms beside large terms | Reduction order/compensation changed | Retain Kahan pragmas and source arithmetic order; check actual state bit pattern on adversarial fixture before simplifying |
| Speculative rewind retains wrong continuation | Conv, recurrent or position metadata restored independently | Restore the coupled saved checkpoint and its offset/padding/lengths; arbitrary recurrent token trim is not this contract |
| Helper says kernel candidate but no kernel ran | Availability and shapes were declarations | Report actual dispatch not_verified; obtain separate native route evidence before interpreting parity or timing |
| Source test exits without exercising desired path | Optional-kernel fallback or unavailable toolchain | Record exact tested branch and not_run gaps; green static tests are not native execution |

Compiler and Apple Swift/MLX/Metal absence remain
**BLOCKED_REQUIRED_BACKEND**. Use the [verification boundaries](verification-boundaries.md)
to plan the next authorized native check. Preserve negative/partial results and
do not turn source claims, helper payload sums or scaffold CI into quality or
performance acceptance.
