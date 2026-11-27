# Inventory gaps at `7626c58f8158986770f0515888572ebb550d1751`

Presence, nonempty values and comparability are counted independently. Comparability is measured against the declared pilot inputs (TTS engine vllm-omni; migration backend ascend, engine version 0.27.1). Blank or prose-only fields leave applicability unknown.

| Field | Present | Nonempty | TTS comparable | Migration comparable |
| --- | ---: | ---: | ---: | ---: |
| backend | 134 | 134 | 0 | 50 |
| hardware | 55 | 37 | 0 | 0 |
| os | 0 | 0 | 0 | 0 |
| model | 0 | 0 | 0 | 0 |
| phase | 0 | 0 | 0 | 0 |
| engine | 0 | 0 | 0 | 0 |
| engine_version | 0 | 0 | 0 | 0 |
| dependency_version | 0 | 0 | 0 | 0 |
| dtype | 0 | 0 | 0 | 0 |
| workload | 0 | 0 | 0 | 0 |
| quality | 0 | 0 | 0 | 0 |
| measurement | 0 | 0 | 0 | 0 |

## Per-entry gaps

All entries are retained. Missing conditions limit transfer conclusions. Read errors prevent quoting the entry until repaired.

- `package:inferrsi.ascend.skills.ascend_aclgraph_capture_replay` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.ascend.skills.ascend_device_health` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.ascend.skills.ascend_distributed_parallel` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.ascend.skills.ascend_graph_mode` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.ascend.skills.ascend_model_adaptation` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.ascend.skills.ascend_operator_profiling` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.ascend.skills.ascend_operator_tuning` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.ascend.skills.ascend_optimization_casebook` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.ascend.skills.ascend_performance_analysis` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.ascend.skills.ascend_video_diffusion_optimization` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.ascend.skills.ascendc_tiling_design` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.assess_serving_preemption` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.assess_split_backward_schedule` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.cuda.skills.audit_afd_p2p_exchanges` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.audit_fixed_workload_claim` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.cuda.skills.audit_flare_session_lifecycle` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.audit_h3_metal_fasth3_semantics` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.audit_h3_runtime_residency` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.audit_llama_runtime_state` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.audit_recurrent_kv_finalization` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.audit_sd_cpp_residency` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.audit_sglang_diffusion_lifetimes` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.audit_vllm_kv_lifetimes` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.bound_windowed_attention_replay` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.budget_speculative_verification` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.calibrate_serving_simulation` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.ascend.skills.cann_attribution_overlap` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `checkout:case.admission-drain-occupancy` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `checkout:case.drama3-rejected-directions` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `checkout:case.qwen-ascend-rejected-directions` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `checkout:case.qwen-b300-rejected-directions` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `checkout:case.sarathi-chunk-budget` — backend, hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `checkout:case.sglang-gdn-source-contract` — backend, hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `checkout:case.vllm-gdn-source-contract` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.cgroup_resource_controls` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.checkpoint_recovery_consistency` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.choose_parallel_training_plan` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.cite_check_downstream_pr` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.claim_contract` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.comfy_ui` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.competitor_scan` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.dcp_async_save_performance` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.dense_performance_evidence` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.cuda.skills.diagnose_attention_bottlenecks` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.diagnose_vllm_admission_pressure` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.diffusers_invocation_state` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.draft_acceptance_issue` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.dwarfstar` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.evaluate_elastic_serving_placement` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.generation_cache_lifecycle` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.host_memory_management` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.host_overhead_optimization` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.cuda.skills.host_overhead_profiling` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.husky` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.inference_benchmark_design` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.inference_optimization_casebook` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.kernel_writing_guide` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.kv_tier_management` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.lazy_evaluation_stream_lifetimes` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.lily` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.lithos_metal` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.local_dream` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.mistral_rs` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.mlc_llm` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.mlx_swift_lm` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.model_sol_analysis` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.npu_skill_factory` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.optimization_search_policy` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.os_process_placement` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.performance_ceiling_analysis` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.plan_activation_residency` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.project_maya` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.pytorch` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.cuda.skills.reason_hopper_kernels` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.repository_evolution_analysis` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.rsi_evidence` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.skill_evolution_playbook` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.splash` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.storage_io_measurement` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.ascend.skills.torch_npu` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.ascend.skills.torchnpu_device_memory_lifecycle` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.ascend.skills.torchnpu_pinned_host_memory_lifecycle` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.training_input_pipeline` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.training_resource_budget` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.video_diffusion_optimization` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.ascend.skills.vllm_ascend` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.vllm_metal` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:inferrsi.common.skills.weight_loading_optimization` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:cache_dit.common.diffusion.residual_cache_calibration` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:deepinfer.common.llm.bounded_windowed_replay` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:deepinfer.common.llm.speculative_verification_budget` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:deepinfer.common.llm.zero_overhead_deferred_scheduling` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:diffusers.cuda.diffusion.group_offload_transfer_overlap` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:flashattention.cuda.attention.generation_specific_dispatch` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:flashinfer.cuda.llm.paged_decode_dispatch` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:lmdeploy.cuda.llm.kv_quantization_capacity_cost` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:mlx.mlx.execution.cross_stream_dependency` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:mlx.mlx.execution.evaluation_completion` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:mlx.mlx.execution.post_detachment_buffer_lifetime` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:pytorch.cuda.compiler.cudagraph_shapes_and_lifetimes` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:qwen3_tts_engine.ascend.audio.codec_constants_and_state` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:qwen3_tts_engine.ascend.audio.fixed_customvoice_prompt` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:qwen3_tts_engine.ascend.audio.graph_batching_state_ownership` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:sglang.common.llm.parallelism_and_extension` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:sglang.common.llm.runtime_radix_hicache` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:sglang.common.llm.tuning_and_validation` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:sglang.cuda.llm.hierarchical_prefix_cache` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:sglang_omni.common.audio.serving_and_streaming_quality` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:sglang_omni.common.omni.extension_lifecycle_validation` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:sglang_omni.common.omni.pipeline_state_and_transport` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:strata.common.llm.architecture_search_space` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:strata.common.llm.controlled_execution_tuning` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:strata.common.llm.engine_validation_contract` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:tensorrt_llm.cuda.llm.prefill_decode_disaggregation` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:transformers.common.llm.kv_cache_strategy_contracts` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:triton.common.kernel.bandwidth_fusion_resource_limits` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:vllm.common.llm.bounded_serving_measurement` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:vllm.common.llm.extension_correctness_gates` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:vllm.common.llm.runtime_and_kv_ownership` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:vllm_omni.ascend.diffusion.minimax_h3_reference_kv_reuse` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:vllm_omni.ascend.diffusion.minimax_h3_sp_head_buckets` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:vllm_omni.ascend.diffusion.qwen_image_21_eager_t2i` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:vllm_omni.common.audio.streaming_serving_measurement` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:vllm_omni.common.diffusion.measurement_and_profiling` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:vllm_omni.common.diffusion.production_integration_gates` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:vllm_omni.common.diffusion.step_state_and_output_validation` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:vllm_omni.common.diffusion.upstream_review_gates` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:vllm_omni.common.omni.stage_ownership_and_search` — hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:vllm_omni.cuda.audio.concurrency_scaling_state_and_overlap` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:vllm_omni.cuda.diffusion.minimax_h3_adaln_schedule_cache` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:vllm_omni.cuda.diffusion.minimax_h3_cuda_mxfp8` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:vllm_omni.cuda.diffusion.minimax_h3_fp32_modulation` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:vllm_omni.cuda.diffusion.minimax_h3_qk_norm_rope` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:vllm_omni.cuda.diffusion.minimax_h3_ref2va_teacache` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:vllm_omni.cuda.diffusion.minimax_h3_vae_stacked_tiling` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
- `package:xdit.cuda.diffusion.parallelism_freshness_and_topology` — os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement
