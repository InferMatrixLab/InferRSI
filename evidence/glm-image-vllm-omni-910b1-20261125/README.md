# Native GLM-Image on two Ascend 910B1s

The performance comparison uses the public vLLM-Omni `Omni.generate` entry point for 512×512 BF16 text-to-image generation. Autoregressive decoding and 20 diffusion steps both contribute to the single-image latency. A fresh engine serves each invocation, with a separate untimed warmup.

The first candidate shares the position tables across local decoder layers. The incremental candidate applies the same rotation to adjacent Q/K heads. The model implementations and focused regression tests are in [vLLM-Omni #11130](https://github.com/vllm-project/vllm-omni/pull/11130). The governing [issue #668](https://github.com/InferMatrixLab/InferRSI/issues/668) records the acceptance conditions and the initial rejected baseline qualification. The [InferRSI decision-view changes](https://github.com/InferMatrixLab/InferRSI/pull/663) are pinned for the incremental round.

The original quality attempt stopped because the stock blue-cover image at seed 771 has very low contrast. The parity cohorts retain the prompt and compare its exact RGB pixels against an independently rendered stock fixture. The benchmark measures latency and preservation of engine output. It does not evaluate prompt adherence or generation quality.

The incremental protocol also renders the teapot at seed 43 in both quality arms, verifies that changing the seed changes the stock RGB output, and compares all four baseline/candidate arrays. The engine hashes the RGB bytes after decoding. PNG compression and engine initialization are outside the timed interval.

The source snapshots, runtime, weights, workload, output oracle and acceptance gates are recorded in `plan/`. The incremental selection and its two alternatives are in `incremental/decision.json`. The 40-layer diagnostics describe the rotary region only. End-to-end AB/BA and independent-final receipts are pending.
