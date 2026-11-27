# Native GLM-Image on two Ascend 910B1s

The performance comparison uses the public vLLM-Omni `Omni.generate` entry point for 512×512 BF16 text-to-image generation. Autoregressive decoding and 20 diffusion steps both contribute to the single-image latency. A fresh engine serves each invocation, with a separate untimed warmup.

The first candidate shares the position tables across local decoder layers. The incremental candidate applies the same rotation to adjacent Q/K heads. The model implementations and focused regression tests are in [vLLM-Omni #11130](https://github.com/vllm-project/vllm-omni/pull/11130). The governing [issue #668](https://github.com/InferMatrixLab/InferRSI/issues/668) records the acceptance conditions and the initial rejected baseline qualification. The [InferRSI decision-view changes](https://github.com/InferMatrixLab/InferRSI/pull/663) are pinned for the incremental round.

The original quality attempt stopped because the stock blue-cover image at seed 771 has very low contrast. The parity cohorts retain the prompt and compare its exact RGB pixels against an independently rendered stock fixture. The benchmark measures latency and preservation of engine output. Prompt adherence remains unqualified.

The incremental protocol also renders the teapot at seed 43 in both quality arms, verifies that changing the seed changes the stock RGB output, and compares all four baseline/candidate arrays. The engine hashes the RGB bytes after decoding. PNG compression and engine initialization are outside the timed interval.

The source snapshots, runtime, weights, workload, output oracle and acceptance gates are recorded in `plan/`. The incremental selection and its two alternatives are in `incremental/decision.json`. The 40-layer diagnostics describe the rotary region only.

### End-to-end results on two Ascend 910B1s

Directly comparing stock with the two commits together on the same reserved card pair gave **57.58 → 49.19 s/image**, a **14.58%** latency reduction (1.171× speedup). The stage timings for these same requests were 52.71 → 44.56 s for autoregressive generation and 4.86 → 4.61 s for diffusion.

| Native GLM-Image comparison | AB/BA round | Independent AB/BA final |
| --- | ---: | ---: |
| Stock → shared position tables | 58.42 → 49.98 s (14.44%) | 59.05 → 49.20 s (16.68%) |
| Shared position tables → joint Q/K rotation | 50.93 → 47.97 s (5.82%) | 51.99 → 48.77 s (6.19%) |

Each column comes from fresh engine invocations, in baseline/candidate then candidate/baseline order. An invocation's score is the median wall time of two fixed prompts. The report shows the median of the two scores per side. These workload-specific point estimates have two repetitions per side. The direct comparison is a separate AB/BA run. Each incremental change also cleared a 3% gate in an independent final.

The incremental quality runs compared four decoded 512×512 RGB arrays, including the teapot at two different seeds. Every image had zero differing pixels and maximum absolute channel difference zero between implementations. Changing the teapot seed changed its reference bytes. Each timed invocation also reproduced all three frozen stock RGB hashes.

The incremental campaign froze InferRSI PR #663 at `1c235ec9`. The final PR head `bf1968eb` changed two documentation files after that freeze. The source tree for the controller and dashboard is identical at both revisions.

From this evidence directory, run `python results/verify.py` to verify the saved result hashes, RGB checks, AB/BA order, summary statistics and comparison verdicts. The per-request stage times and image hashes are in `results/trials.json`, `incremental/trials.json` and `results/direct-stock-packed.json`.
