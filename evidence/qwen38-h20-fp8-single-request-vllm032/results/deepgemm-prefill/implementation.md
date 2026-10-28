# DeepGEMM prefill without checkpoint requantization

Historical implementation snapshot before build attempts2061/2077 and extraction2083. See the adjacent build-failure and extraction records for later outcomes.

Scope: InferRSI acceptance Issue67, Qwen3.8 official FP8 independent engine.
Date2026-10-23; state candidate; verdict INCONCLUSIVE for GPU/model/service claims.

The owner prioritized performance implementation while the first FlashInfer GPU measurement waits for allocation. This separate model-plane slice replaces M>=32 prefill GEMM only under the explicit flashinfer_deepgemm option. M<32 retains FlashInfer. Default and FlashInfer-only modes retain their existing compute paths.

vLLM0.32.0 pins vllm-project/DeepGEMM1e1842a833699298f7afc02eefb2ed168fff6938. Its SM90 API accepts FP32 per-token/block128 activation scales and contiguous FP32 block128 weight scales. vLLM's optional E8M0 preprocessing can dequantize/requantize weights; copying that behavior would violate this campaign's original-weight constraint. The new adapter explicitly uses recipe(1,128,128), disable_ue8m0_cast=True, original E4M3 weights and unchanged multipliers. It imports external deep_gemm and has no vLLM-runtime fallback.

The new Triton quantizer uses the old native formula max(abs(x))/448 and division by max(scale,1e-12), writing FP32 SFA at stride(1,ceil(M/4)*4). This preserves the existing native policy, not a claim of bit-identical vLLM quantization: the inspected upstream helper clamps amax differently. No E8M0 rounding or weight transformation is introduced.

Implementation b412062e13c92d2429b3758ca39af7439df4f7ec is based on8859ef319486eb5ed4a444fc66c1018cbebbab33 and pushed as nano-vllm PR12, dependent onPR11. CPU Slurm2054 completed0:0 in16s,8CPU/0GPU;115 tests passed in11.93s and allocation released. The independent reviewer verified exact patch identity, API/layout/recipe compatibility, CPU log and scheduler receipt. No blocking interface/dispatch defect found. A stale large-prefill comment is a minor pending cleanup.

Important test gap: CPU tests mock the activation quantizer. They do not execute its Triton code, TMA loads or DeepGEMM GEMM. The target runtime currently contains only vLLM's vendored package, not independent deep_gemm. CPU-only Slurm2061 is building the exact pinned standalone source, with pinned submodules, against the unchanged baseline Torch environment. A task-owned uv-installed wheel-only build overlay supplies the missing build tool; no baseline package mutation is intended, and before/after freeze comparison is required. Build outcome and binary identity are pending.

No DeepGEMM GPU job is submitted. Next GPU controls must include M32/M33, multiple K blocks, zero/tiny activations and nonuniform scales, plus actual projection shapes; then exact8192/2048 HTTP measurement under the same physical device/runtime. Keep compilation, numerical, resource and performance failures distinct. No microbenchmark or CPU check can award service gain or final parity; task-quality and full formal acceptance remain outstanding.
