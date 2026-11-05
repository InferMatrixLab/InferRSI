# Release readset

Source: [vllm-project/vllm-ascend, v0.27.1rc1](https://github.com/vllm-project/vllm-ascend/tree/3b31886237ed65c435e0965b10e8002ff5769766). The tag resolves to `3b31886237ed65c435e0965b10e8002ff5769766`. All links below use that commit. The root license is Apache-2.0. The procedures are original summaries; checkpoint and dependency licenses are separate.

| Source | Anchor |
| --- | --- |
| [LICENSE](https://github.com/vllm-project/vllm-ascend/blob/3b31886237ed65c435e0965b10e8002ff5769766/LICENSE#L1) | `Apache License` |
| [docs/source/user_guide/release_notes.md](https://github.com/vllm-project/vllm-ascend/blob/3b31886237ed65c435e0965b10e8002ff5769766/docs/source/user_guide/release_notes.md#L3) | `## v0.27.1rc1` |
| [setup.py](https://github.com/vllm-project/vllm-ascend/blob/3b31886237ed65c435e0965b10e8002ff5769766/setup.py#L519) | `"vllm.platform_plugins"` |
| [vllm_ascend/__init__.py](https://github.com/vllm-project/vllm-ascend/blob/3b31886237ed65c435e0965b10e8002ff5769766/vllm_ascend/__init__.py#L51) | `def _ensure_global_patch` |
| [vllm_ascend/models/__init__.py](https://github.com/vllm-project/vllm-ascend/blob/3b31886237ed65c435e0965b10e8002ff5769766/vllm_ascend/models/__init__.py#L4) | `def register_model` |
| [vllm_ascend/platform.py](https://github.com/vllm-project/vllm-ascend/blob/3b31886237ed65c435e0965b10e8002ff5769766/vllm_ascend/platform.py#L622) | `def _configure_minimax_m3_a5_mixed_kv_cache` |
| [vllm_ascend/models/minimax_m3/minimax_m3.py](https://github.com/vllm-project/vllm-ascend/blob/3b31886237ed65c435e0965b10e8002ff5769766/vllm_ascend/models/minimax_m3/minimax_m3.py#L123) | `def _resolve_layer_kv_cache_dtype(` |
| [vllm_ascend/models/minimax_m3/msa_m3.py](https://github.com/vllm-project/vllm-ascend/blob/3b31886237ed65c435e0965b10e8002ff5769766/vllm_ascend/models/minimax_m3/msa_m3.py#L169) | `class AscendMiniMaxM3IndexerCache` |
| [docs/source/tutorials/models/MiniMax-M3.md](https://github.com/vllm-project/vllm-ascend/blob/3b31886237ed65c435e0965b10e8002ff5769766/docs/source/tutorials/models/MiniMax-M3.md#L23) | `MiniMax-M3-MXFP8` |
| [tests/ut/test_platform.py](https://github.com/vllm-project/vllm-ascend/blob/3b31886237ed65c435e0965b10e8002ff5769766/tests/ut/test_platform.py#L166) | `def test_a5_minimax_m3_fp8_preserves_explicit_cache_skip_layers` |
| [tests/ut/models/minimax_m3/test_msa_m3.py](https://github.com/vllm-project/vllm-ascend/blob/3b31886237ed65c435e0965b10e8002ff5769766/tests/ut/models/minimax_m3/test_msa_m3.py#L221) | `def test_m3_kv_cache_dtype_skip_layers_keeps_gqa_bf16_and_msa_fp8` |
| [tests/e2e/pull_request/one_card/test_minimax_m3_sparse_attn.py](https://github.com/vllm-project/vllm-ascend/blob/3b31886237ed65c435e0965b10e8002ff5769766/tests/e2e/pull_request/one_card/test_minimax_m3_sparse_attn.py#L608) | `def test_decode_index_topk_correctness` |
| [docs/source/tutorials/models/DeepSeek-V4-Flash.md](https://github.com/vllm-project/vllm-ascend/blob/3b31886237ed65c435e0965b10e8002ff5769766/docs/source/tutorials/models/DeepSeek-V4-Flash.md#L1133) | `This section shows an 1P1D deployment on two Ascend 950DT` |
| [vllm_ascend/spec_decode/dspark_proposer.py](https://github.com/vllm-project/vllm-ascend/blob/3b31886237ed65c435e0965b10e8002ff5769766/vllm_ascend/spec_decode/dspark_proposer.py#L23) | `class AscendDSparkProposer` |
| [tests/e2e/pull_request/four_card/spec_decode/test_dspark_deepseekv4.py](https://github.com/vllm-project/vllm-ascend/blob/3b31886237ed65c435e0965b10e8002ff5769766/tests/e2e/pull_request/four_card/spec_decode/test_dspark_deepseekv4.py#L75) | `def test_deepseek_v4_dspark_acceptance_tp4` |
| [tests/e2e/pull_request/utils.py](https://github.com/vllm-project/vllm-ascend/blob/3b31886237ed65c435e0965b10e8002ff5769766/tests/e2e/pull_request/utils.py#L240) | `def _run_speculative_decoding` |
| [tests/0.27.1rc_vllm-ascend_overall_conclusion_release_notes_EN.md](https://github.com/vllm-project/vllm-ascend/blob/3b31886237ed65c435e0965b10e8002ff5769766/tests/0.27.1rc_vllm-ascend_overall_conclusion_release_notes_EN.md#L3) | `## 1. Model Validation` |

The release notes supply the RC scope. The test-summary filename mentions 0.27.1rc but its heading says V0.27.0RC1. Treat its scenarios as attributable upstream context; do not promote its numbers to results for this pin. The model tutorials include examples from multiple releases. Test parameterizations establish what a future run would check.

Repo-to-Skill construction used release scope → selected producer/consumer paths → test oracles → packaged procedures. Upstream NPU tests, model quality, sustained service performance and held-out skill efficacy remain unmeasured here.
