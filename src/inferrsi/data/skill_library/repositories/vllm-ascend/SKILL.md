---
name: vllm-ascend
description: "Diagnose vLLM Ascend v0.27.1rc1 plugin registration, MiniMax-M3 mixed KV-cache dtypes, and DeepSeek-V4-Flash DSpark prefill/decode configuration on the documented release hardware."
---

# Diagnose an Ascend release-candidate serving path

Start with the plugin revision, upstream vLLM version, actual device profile, model and draft checkpoint revisions, failure phase and the effective configuration on each role. Use the release table to classify the deployment before borrowing a tutorial or test command.

| Model | Release-reported configuration | First comparison |
| --- | --- | --- |
| MiniMax-M3 | Atlas 800 A3 W8A8 or 950DT W8A8C8, including two-node 1P1D | Separate weight format, sparse-cache storage and dense-cache storage. |
| DeepSeek-V4-Flash | 950DT W4A8C8, two-node 1P1D DSpark and KV Cache Pool | Compare checkpoint draft budget, connector topology and graph mode on each role. |

The tag pairs with upstream vLLM **v0.27.1**. Its release stack lists HDK 26.1.1, CANN 9.1.0, PyTorch 2.10.0, torch_npu 2.10.0.post4 and Triton Ascend 3.2.2. Images use Python 3.12 and Mooncake 0.3.11.post1. Record the installed stack separately. For A2 or another model, report the combination as outside this RC's declared scope and identify the version that owns any example you use.

## Select the first failing boundary

- Engine initialization or unknown architecture → [trace plugin discovery into the engine process](references/plugin-registration.md).
- MiniMax-M3 starts with FP8 requested but some layers allocate BF16, or top-k results differ → [inspect the effective layer policy and its consumers](references/minimax-cache.md).
- DeepSeek-V4-Flash starts on each node but DSpark acceptance or PD generation fails → [reconcile draft, connector and capture settings](references/dspark-pd.md).

Return the first discrepancy, its source locator, the effective values on the affected worker or rank, the smallest distinguishing check, and the evidence still needed. Keep initialization, token correctness, acceptance length and sustained service throughput as separate observations. This is a source-derived candidate. Consult the [pinned readset](references/sources.md) for provenance and native validation limits.
