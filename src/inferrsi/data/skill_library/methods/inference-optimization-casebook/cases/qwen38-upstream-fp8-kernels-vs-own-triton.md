# A self-written block-scaled FP8 GEMM was 100x slower than the upstream kernel

A dedicated engine shipped a Triton block-scaled FP8 GEMM that padded 32
singleton lanes into an M64 tile to keep numerics stable. It ran at 2.8 TFLOPS
on H20-3e and made an 8K prefill take 145 s. Measuring the upstream libraries on
the same shapes turned the build-versus-borrow decision into arithmetic.

| Implementation | 8192x17408x5120 | Note |
| --- | --- | --- |
| Own Triton block-scaled kernel | 2.8 TFLOPS | ~1% of FP8 peak |
| FlashInfer block-scaled (installed from PyPI, Apache-2.0) | 273 TFLOPS | usable in the engine environment |
| DeepGEMM (vendored inside vLLM, prebuilt `.so`) | 279 TFLOPS | unusable outside vLLM's environment: the extension pins a torch minor version |

Thresholds were registered before the measurement: go at >=280 TFLOPS, abandon
below 250. FlashInfer measured 273, so it was adopted with the 2.5% shortfall
recorded rather than rounded away. The same library reports 3273 GB/s for M=1,
which makes it a candidate for the bandwidth-bound decode path as well.

Two traps worth recording. `pip install deep_gemm` resolves to an unrelated
18 KB placeholder on PyPI; the real project is source-only. And a vendored
extension compiled against one torch minor version fails at import on another,
so "reuse the dependency of the reference server" is not a shortcut.

Disposition: measure the upstream implementation on your own shapes before
writing a kernel whose only claim is numerical caution. Register the go/abandon
threshold first; record the shortfall if you adopt below it.

Revisit condition: new shapes, a different accelerator, or a new upstream
release. First check: rerun the shape sweep and confirm the largest shapes still
sit near peak before reusing this decision.

Applicability: SM90-class device, FP8 e4m3 with 128x128 block scales, torch 2.14
engine environment. The M=1 numbers are microbenchmarks, not end-to-end decode.

Limitations: single-card microbenchmarks; end-to-end prefill was measured
separately; upstream versions may change both the numbers and the licensing.

Retained records: the 2.8 / 273 / 279 TFLOPS table, 3273 GB/s at M=1, the 280
TFLOPS go line, the 2.5% shortfall, the placeholder package and the torch pin
are Issue #67 comment 6336720892 (body sha256
`37b84900b48fc5da201792c280519969514d2bbed0afe75a3c4ef56329077201`). 2.8 TFLOPS
at M=8192 and the 145 s prefill are also in
[nano-vllm pull request 3](https://github.com/jiangkuaixue123/nano-vllm/pull/3)
(body sha256 `172d437e2772a4e5aefff1f9a03a4fd381f6b11e0c12e0821eb2541c5c568c34`);
the same day's ledger withdraws 145.3 s because it includes first-call JIT.
Comment 6336567189 records 279 against the 280 line. The located ledger does
not contain an abandon-below-250 threshold.
