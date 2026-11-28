---
name: vllm-ascend
description: "Analyze vLLM Ascend v0.27.1rc1 performance and commit evolution for DeepSeek-V4, Kimi K3, MiniMax-M3 and GLM5+, fused operators, DSA-CP, FlashComm1, Fused-MC2 and DSpark, with effective dispatch, rollback and test-oracle guidance."
metadata:
  inferrsi: |
    {
      "profile": "local-skill-v1",
      "schema_version": 1,
      "kind": "skill",
      "origin": [
        "external"
      ],
      "status": "candidate",
      "empirical_validation": "not_run",
      "tags": [
        "vllm-ascend",
        "v0.27.1rc1",
        "MiniMax-M3",
        "FP8",
        "KV cache",
        "DeepSeek-V4-Flash",
        "DSpark",
        "PD",
        "plugin registration",
        "DeepSeek-V4",
        "Kimi K3",
        "MiniMax M3",
        "GLM5",
        "GLM5.1",
        "GLM5.2",
        "GLM5.3",
        "DSA-CP",
        "FlashComm1",
        "Fused-MC2",
        "fusion",
        "performance",
        "commit-history"
      ],
      "sources": [
        {
          "type": "git",
          "url": "https://github.com/vllm-project/vllm-ascend",
          "commit": "3b31886237ed65c435e0965b10e8002ff5769766",
          "license": "Apache-2.0",
          "paths": [
            "LICENSE",
            "docs/source/tutorials/models/DeepSeek-V4-Flash.md",
            "docs/source/tutorials/models/MiniMax-M3.md",
            "docs/source/user_guide/release_notes.md",
            "setup.py",
            "tests/0.27.1rc_vllm-ascend_overall_conclusion_release_notes_EN.md",
            "tests/e2e/nightly/single_node/ops/multicard_ops_a3/test_sfa_cp_a2a.py",
            "tests/e2e/nightly/single_node/ops/singlecard_ops/test_chunk_kda_aclnn.py",
            "tests/e2e/nightly/single_node/ops/singlecard_ops/test_fused_sparse_attention_overlap.py",
            "tests/e2e/nightly/single_node/ops/singlecard_ops/test_kimi_k3_situ_fusion_cases.py",
            "tests/e2e/nightly/single_node/ops/singlecard_ops/triton/test_copy_and_expand_dflash_dspark.py",
            "tests/e2e/nightly/single_node/ops/singlecard_ops/triton/test_kimi_k3_fusions.py",
            "tests/e2e/nightly/single_node/ops/singlecard_ops/triton/test_split_qkv_tp_rmsnorm_rope.py",
            "tests/e2e/pull_request/eight_card/model_runner_v2/test_glm5_2.py",
            "tests/e2e/pull_request/eight_card/test_glm5_2.py",
            "tests/e2e/pull_request/four_card/context_parallel/test_accuracy.py",
            "tests/e2e/pull_request/four_card/spec_decode/test_dspark_deepseekv4.py",
            "tests/e2e/pull_request/one_card/compile/test_norm_quant_fusion.py",
            "tests/e2e/pull_request/one_card/test_minimax_m3_sparse_attn.py",
            "tests/e2e/pull_request/sixteen_card/test_kimi_k3.py",
            "tests/e2e/pull_request/utils.py",
            "tests/ut/attention/test_dsa_v1.py",
            "tests/ut/attention/test_dsv4_block_geometry.py",
            "tests/ut/kv_transfer/test_layerwise_multi_cache_spec.py",
            "tests/ut/models/minimax_m3/test_minimax_m3_eplb.py",
            "tests/ut/models/minimax_m3/test_msa_m3.py",
            "tests/ut/models/test_kimi_k3_adapter.py",
            "tests/ut/ops/test_kimi_kda.py",
            "tests/ut/patch/platform/test_patch_parallel_config.py",
            "tests/ut/patch/platform/test_prefix_cache_cp_patches.py",
            "tests/ut/quantization/methods/test_fp8_block.py",
            "tests/ut/spec_decode/test_dspark_speculator.py",
            "tests/ut/spec_decode/test_llm_base_proposer.py",
            "tests/ut/test_ascend_config.py",
            "tests/ut/test_ascend_forward_context.py",
            "tests/ut/test_platform.py",
            "tests/ut/worker/test_device_metadata.py",
            "tests/ut/worker/test_model_runner_v1.py",
            "vllm_ascend/__init__.py",
            "vllm_ascend/ascend_config.py",
            "vllm_ascend/ascend_forward_context.py",
            "vllm_ascend/attention/context_parallel/dsa_cp.py",
            "vllm_ascend/attention/dsa_attn_kv_plan.py",
            "vllm_ascend/attention/mla_v1.py",
            "vllm_ascend/attention/sfa_v1.py",
            "vllm_ascend/attention/sparse_flash_mla.py",
            "vllm_ascend/compilation/graph_fusion_pass_manager.py",
            "vllm_ascend/compilation/passes/muls_add_pass.py",
            "vllm_ascend/compilation/passes/norm_quant_fusion_pass.py",
            "vllm_ascend/compilation/passes/qknorm_rope_fusion_pass.py",
            "vllm_ascend/core/kv_cache_interface.py",
            "vllm_ascend/device/device_op.py",
            "vllm_ascend/lora/fused_moe.py",
            "vllm_ascend/models/__init__.py",
            "vllm_ascend/models/common/ops/sequence_parallel.py",
            "vllm_ascend/models/deepseek_v4/compressor.py",
            "vllm_ascend/models/deepseek_v4/indexer.py",
            "vllm_ascend/models/deepseek_v4/model.py",
            "vllm_ascend/models/minimax_m3/minimax_m3.py",
            "vllm_ascend/models/minimax_m3/msa_m3.py",
            "vllm_ascend/models/minimax_m3/ops/msa_m3_npu.py",
            "vllm_ascend/ops/fused_moe/moe_comm_method.py",
            "vllm_ascend/ops/fused_moe/moe_mlp.py",
            "vllm_ascend/ops/fused_moe/token_dispatcher.py",
            "vllm_ascend/ops/gdn.py",
            "vllm_ascend/ops/kimi_kda.py",
            "vllm_ascend/ops/rope_dsv4.py",
            "vllm_ascend/ops/triton/docs/sfa_cp_a2a_fused.md",
            "vllm_ascend/ops/triton/dsa_cp.py",
            "vllm_ascend/patch/platform/patch_parallel_config.py",
            "vllm_ascend/patch/worker/patch_deepseek_v2.py",
            "vllm_ascend/patch/worker/patch_minimax_m2.py",
            "vllm_ascend/platform.py",
            "vllm_ascend/quantization/configs/modelslim_config.py",
            "vllm_ascend/sample/sampler.py",
            "vllm_ascend/spec_decode/dspark_proposer.py",
            "vllm_ascend/spec_decode/llm_base_proposer.py",
            "vllm_ascend/utils.py",
            "vllm_ascend/worker/device_metadata.py",
            "vllm_ascend/worker/v2/spec_decode/dspark/speculator.py"
          ],
          "readset": "references/sources.md"
        }
      ],
      "provenance_readsets": [
        "references/sources.md",
        "references/history-scope.md",
        "references/history-reviewed.json"
      ],
      "consumption_mode": "packaged",
      "applicability": {
        "scope": "Release-pinned performance diagnosis and historical optimization analysis for DeepSeek-V4, Kimi K3, MiniMax-M3, GLM5+, fusion and communication/speculation paths.",
        "prerequisites": "Pinned release evidence or a matching installed stack and role-specific logs.",
        "input_contract": "Source and checkpoint revisions, quantization metadata, device and operators, V1/V2 runner, P/D role, TP/DP/PP/PCP/DCP, requested versus derived config, dominant phase and numerical/performance traces.",
        "produced_artifact": "First failing boundary with effective values, source locator and smallest discriminating check.",
        "refusal_point": "Report an evidence gap when package, role, cache dtype or release identity cannot be established."
      },
      "recommendations": [
        "Check the registered general hook in the failing process.",
        "Resolve the per-layer cache skip set before interpreting FP8 storage.",
        "Compare both DSpark role budgets and connector layouts before changing capture tiers.",
        "Check optimization reversals and exact current dispatch before reusing an old performance change.",
        "Use commit history for provenance and numerical or serving oracles for validation."
      ],
      "limitations": [
        "Source-derived guidance for the selected release paths only.",
        "Native NPU execution, performance and behavioral skill evaluation not run."
      ]
    }
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
