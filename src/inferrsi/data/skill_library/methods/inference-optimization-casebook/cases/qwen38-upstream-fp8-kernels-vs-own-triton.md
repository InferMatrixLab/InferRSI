# A self-written block-scaled FP8 GEMM was 100x slower than the upstream kernel

Kind, origin, state and source identities belong to the
[typed source and scope record](qwen38-upstream-fp8-kernels-vs-own-triton.json).

A dedicated engine shipped a Triton block-scaled FP8 GEMM that padded 32
singleton lanes into an M64 tile to keep numerics stable. It ran at 2.8 TFLOPS
on H20-3e. An 8K prefill was also reported at 145 s; the same day's ledger
withdraws 145.3 s because that sample includes first-call JIT and is not timing
evidence. Measuring the upstream libraries on the same shapes turned the
build-versus-borrow decision into arithmetic.

| Implementation | 8192x17408x5120 | Note |
| --- | --- | --- |
| Own Triton block-scaled kernel | 2.8 TFLOPS | ~1% of FP8 peak |
| FlashInfer block-scaled (installed from PyPI, Apache-2.0) | 273 TFLOPS | usable in the engine environment |
| DeepGEMM (vendored inside vLLM, prebuilt `.so`) | 279 TFLOPS | unusable outside vLLM's environment: the extension pins a torch minor version |

The located ledger registers one go line before the measurement: >=280 TFLOPS.
FlashInfer measured 273 and DeepGEMM measured 279, so FlashInfer was adopted
with the 2.5% shortfall recorded rather than rounded away. An abandon-below-250
line is not in those records, so this case does not treat 250 as a registered
threshold. The same library reports 3273 GB/s for M=1, which makes it a
candidate for the bandwidth-bound decode path as well.

Two traps worth recording. `pip install deep_gemm` resolves to an unrelated
18 KB placeholder on PyPI; the real project is source-only. And a vendored
extension compiled against one torch minor version fails at import on another,
so "reuse the dependency of the reference server" is not a shortcut.

Disposition: measure the upstream implementation on your own shapes before
writing a kernel whose only claim is numerical caution. Register the go line
first; record the shortfall if you adopt below it. Do not cite the withdrawn
145 s sample as prefill timing.

Revisit condition: new shapes, a different accelerator, or a new upstream
release. First check: rerun the shape sweep and confirm the largest shapes still
sit near peak before reusing this decision.

Applicability: SM90-class device, FP8 e4m3 with 128x128 block scales, torch 2.14
engine environment. The M=1 numbers are microbenchmarks, not end-to-end decode.

Limitations: single-card microbenchmarks; end-to-end prefill was measured
separately; upstream versions may change both the numbers and the licensing.

Retained records, with digests in the typed record: the 2.8 / 273 / 279 TFLOPS
table, 3273 GB/s at M=1, the 280 TFLOPS go line, the 2.5% shortfall, the
placeholder package and the torch pin are
[Issue #67](https://github.com/InferMatrixLab/InferRSI/issues/67) comment
6336720892. The withdrawn 145 s report is in
[nano-vllm pull request 3](https://github.com/jiangkuaixue123/nano-vllm/pull/3).
Comment 6336567189 records 279 against the 280 line and does not register 250.
