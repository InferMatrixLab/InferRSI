# FlashInfer small-M FP8 engine integration

Governing acceptance: InferRSI Issue #67. Date: 2026-10-23.
Status: candidate; service performance and model quality INCONCLUSIVE.

The owner explicitly prioritized starting engine performance optimization and parking further evaluator diagnosis. Implement one model-plane hypothesis: opt-in FlashInfer SM90 GEMM for M<32, preserving the existing Triton prefill path. The prior observation that a FlashInfer environment label did not change dispatch motivated binding selection to module construction and reporting actual dispatch counters. Python counters cover warmup/capture and exclude Graph replay.

Pinned vLLM 0.32.0 source uses BF16 activations, official E4M3 weights and FP32 block multipliers in its FlashInfer small-M call. Its larger-M path uses DeepGEMM; that is not implemented in this slice. Installed FlashInfer 0.7.0.post1 source confirms K multiple128, N multiple64 and ceil(N/128) by K/128 per-block scales. Its workspace allocation and cold JIT require actual warmed CUDA Graph verification; code inspection alone does not qualify this path.

Engine commit 8859ef319486eb5ed4a444fc66c1018cbebbab33, base 3e918df2dd7b478d3d2985350bb5efb523ea4981, is pushed as nano-vllm PR11. CPU Slurm2037 completed exit0 in14s, 108 tests passed in11.05s, 8CPU/0GPU, allocation released. Tests cover shape boundary, unchanged scale objects, missing dependency failure, constructed-backend reporting and loader/service/runner regressions. Mocked dispatch is not CUDA evidence.

Attempts retained:
- GPU2038: frozen v1 observer submitted but stayed pending for resources; cancelled before allocation,0GPU. Independent review identified an observer regression: it required one token per SSE choice, although vLLM may merge tokens. This was not an engine failure or measured performance result.
- GPU2040: v2 observer had an unmatched parenthesis; AST/Ruff rejected it locally. The caller shell failed to stop and still submitted. It was cancelled while pending,0GPU. Preserve this tooling failure; future submission follows separate successful syntax checks.
- Prospective v3 corrects the observer, requires one final DONE, counts exact output token IDs/usage and accepts multiple tokens per choice, with ITL counted by choice event. OMP override is removed. AST/Ruff/bash syntax checks passed. Slurm2041 was submitted after successful syntax checks and is pending resources/priority; actual GPU results remain pending.

The bounded experiment requests1H20/30min from authorized readiness, leaving prior usage2388/7200GPU-seconds unchanged until allocation. All arms use the existing vLLM runtime environment without dependency mutation; historical native-runtime results are not a matched control. Six operator shapes check finite outputs and changed-input Graph/eager equality. Then each native Triton/native FlashInfer/vLLM arm uses the same official client, fixed n8192-s0,16-output warmup and2048-output measured request, ignoringEOS, concurrency1. Retain all output IDs, raw SSE, timings, source identities and cleanup.

A single case is an engineering feasibility observation, not the formal10-case/3-repeat matrix, a speedup claim, task-quality qualification or final parity. Full evaluator qualification and statistical approval remain pending. Next decision: inspect actual operator and HTTP results before promoting or rejecting this implementation; preserve any failure with its own scope. No reusable knowledge promotion occurs.

Independent reviewer inspected exact engine head/base and installed FlashInfer source, confirmed the CPU log, verified all five v3 freeze hashes, and exercised four observer controls (merged tokens accepted; duplicate DONE, post-DONE data and incorrect ITL count rejected). Recommendation: proceed with the bounded GPU diagnostic, without quality/performance qualification.

Knowledge candidate: `store:case.qwen38-flashinfer-small-m-integration-cand`, initial retained revision `sha256:481253f455d97aed6f15db825cbaf2f4c71a6f18d80c421f53bf442495405c77`; this public status supplements the initial pending proposal.
