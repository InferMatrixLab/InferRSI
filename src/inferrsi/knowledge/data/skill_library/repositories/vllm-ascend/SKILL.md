---
name: vllm-ascend
description: "Analyze vLLM Ascend v0.27.1rc1 performance and commit evolution for DeepSeek-V4, Kimi K3, MiniMax-M3 and GLM5+, fused operators, DSA-CP, FlashComm1, Fused-MC2 and DSpark, with effective dispatch, rollback and test-oracle guidance."
---

# Investigate release-specific Ascend performance

Start with the plugin revision, upstream vLLM version, actual device profile, model and draft checkpoint revisions, failure phase and the effective configuration on each role. Use the release table to classify the deployment before borrowing a tutorial or test command.

| Model | Release-reported configuration | First comparison |
| --- | --- | --- |
| MiniMax-M3 | Atlas 800 A3 W8A8 or 950DT W8A8C8, including two-node 1P1D | Separate weight format, sparse-cache storage and dense-cache storage. |
| DeepSeek-V4-Flash | 950DT W4A8C8, two-node 1P1D DSpark and KV Cache Pool | Compare checkpoint draft budget, connector topology and graph mode on each role. |

The tag pairs with upstream vLLM **v0.27.1**. Its release stack lists HDK 26.1.1, CANN 9.1.0, PyTorch 2.10.0, torch_npu 2.10.0.post4 and Triton Ascend 3.2.2. Images use Python 3.12 and Mooncake 0.3.11.post1. Record the installed stack separately. For A2 or another model, report the combination as outside this RC's declared scope and identify the version that owns any example you use.

## Select the performance question

| Question | Load first | Required discriminator |
| --- | --- | --- |
| DeepSeek-V4 support through performance evolution | [DSV4 and DSpark evolution](references/deepseek-v4-evolution.md) | Current attention/indexer/compressor path, metadata lifecycle and target/draft ownership |
| DSA-CP, FlashComm1 or Fused-MC2 enabled but ineffective | [Configuration and communication](references/communication-config.md) | Requested values versus normalized SP state, hardware dispatch, rollback and conflicting options |
| Fusion opportunity or fusion performance regression | [Fused operators](references/fused-operators.md) | Graph match or actual kernel dispatch, dtype/layout constraints and current replacement path |
| Kimi K3, MiniMax-M3 or GLM5-family optimization | [Model performance](references/model-performance.md) | Specific checkpoint quantization, attention family, runner and phase |
| Trace an old optimization or audit history coverage | [History scope and review levels](references/history-scope.md) | Reachable candidate versus inspected mechanism versus retained behavior |

Kimi K3 and GLM5-family material describes source implementations within the pinned history. The RC release table above retains its separate validation scope. GLM coverage focuses on GLM5 and later variants present at this tag.

For an optimization proposal, return the relevant commit, mechanism, current eligibility, rollback or superseding change, closest numerical oracle, and a same-workload measurement plan. Check both producer and consumer before recommending a historical optimization. Distinguish operator timing, model quality, speculative acceptance and sustained service results.

## Select the first failing boundary

- Engine initialization or unknown architecture → [trace plugin discovery into the engine process](references/plugin-registration.md).
- MiniMax-M3 starts with FP8 requested but some layers allocate BF16, or top-k results differ → [inspect the effective layer policy and its consumers](references/minimax-cache.md).
- DeepSeek-V4-Flash starts on each node but DSpark acceptance or PD generation fails → [reconcile draft, connector and capture settings](references/dspark-pd.md).

Return the first discrepancy, its source locator, the effective values on the affected worker or rank, the smallest distinguishing check, and the evidence still needed. Keep initialization, token correctness, acceptance length and sustained service throughput as separate observations. This is a source-derived candidate. Consult the [pinned readset](references/sources.md) for provenance and native validation limits.
