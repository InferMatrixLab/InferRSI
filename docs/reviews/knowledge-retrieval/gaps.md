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

### 97 entries

hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement

- `package:inferrsi.ascend.skills.ascend_aclgraph_capture_replay`
- `package:inferrsi.ascend.skills.ascend_distributed_parallel`
- `package:inferrsi.ascend.skills.ascend_graph_mode`
- `package:inferrsi.ascend.skills.ascend_model_adaptation`
- `package:inferrsi.ascend.skills.ascend_operator_profiling`
- `package:inferrsi.ascend.skills.ascend_operator_tuning`
- `package:inferrsi.ascend.skills.ascend_optimization_casebook`
- `package:inferrsi.ascend.skills.ascend_performance_analysis`
- `package:inferrsi.ascend.skills.ascendc_tiling_design`
- `package:inferrsi.common.skills.assess_serving_preemption`
- `package:inferrsi.common.skills.assess_split_backward_schedule`
- `package:inferrsi.cuda.skills.audit_afd_p2p_exchanges`
- `package:inferrsi.common.skills.audit_fixed_workload_claim`
- `package:inferrsi.cuda.skills.audit_flare_session_lifecycle`
- `package:inferrsi.common.skills.audit_h3_metal_fasth3_semantics`
- `package:inferrsi.common.skills.audit_h3_runtime_residency`
- `package:inferrsi.common.skills.audit_llama_runtime_state`
- `package:inferrsi.common.skills.audit_recurrent_kv_finalization`
- `package:inferrsi.common.skills.audit_sd_cpp_residency`
- `package:inferrsi.common.skills.audit_sglang_diffusion_lifetimes`
- `package:inferrsi.common.skills.audit_vllm_kv_lifetimes`
- `package:inferrsi.common.skills.calibrate_serving_simulation`
- `package:inferrsi.ascend.skills.cann_attribution_overlap`
- `checkout:case.admission-drain-occupancy`
- `checkout:case.drama3-rejected-directions`
- `checkout:case.qwen-ascend-rejected-directions`
- `checkout:case.qwen-b300-rejected-directions`
- `checkout:case.vllm-gdn-source-contract`
- `package:inferrsi.common.skills.cgroup_resource_controls`
- `package:inferrsi.common.skills.checkpoint_recovery_consistency`
- `package:inferrsi.common.skills.choose_parallel_training_plan`
- `package:inferrsi.common.skills.cite_check_downstream_pr`
- `package:inferrsi.common.skills.claim_contract`
- `package:inferrsi.common.skills.comfy_ui`
- `package:inferrsi.common.skills.competitor_scan`
- `package:inferrsi.common.skills.dcp_async_save_performance`
- `package:inferrsi.common.skills.dense_performance_evidence`
- `package:inferrsi.cuda.skills.diagnose_attention_bottlenecks`
- `package:inferrsi.common.skills.diagnose_vllm_admission_pressure`
- `package:inferrsi.common.skills.diffusers_invocation_state`
- `package:inferrsi.common.skills.draft_acceptance_issue`
- `package:inferrsi.common.skills.dwarfstar`
- `package:inferrsi.common.skills.evaluate_elastic_serving_placement`
- `package:inferrsi.common.skills.generation_cache_lifecycle`
- `package:inferrsi.common.skills.host_memory_management`
- `package:inferrsi.common.skills.host_overhead_optimization`
- `package:inferrsi.cuda.skills.host_overhead_profiling`
- `package:inferrsi.common.skills.husky`
- `package:inferrsi.common.skills.inference_benchmark_design`
- `package:inferrsi.common.skills.inference_optimization_casebook`
- `package:inferrsi.common.skills.kv_tier_management`
- `package:inferrsi.common.skills.lazy_evaluation_stream_lifetimes`
- `package:inferrsi.common.skills.lily`
- `package:inferrsi.common.skills.lithos_metal`
- `package:inferrsi.common.skills.local_dream`
- `package:inferrsi.common.skills.mistral_rs`
- `package:inferrsi.common.skills.mlc_llm`
- `package:inferrsi.common.skills.mlx_swift_lm`
- `package:inferrsi.common.skills.npu_skill_factory`
- `package:inferrsi.common.skills.optimization_search_policy`
- `package:inferrsi.common.skills.os_process_placement`
- `package:inferrsi.common.skills.plan_activation_residency`
- `package:inferrsi.common.skills.project_maya`
- `package:inferrsi.common.skills.pytorch`
- `package:inferrsi.cuda.skills.reason_hopper_kernels`
- `package:inferrsi.common.skills.repository_evolution_analysis`
- `package:inferrsi.common.skills.rsi_evidence`
- `package:inferrsi.common.skills.skill_evolution_playbook`
- `package:inferrsi.common.skills.splash`
- `package:inferrsi.common.skills.storage_io_measurement`
- `package:inferrsi.ascend.skills.torchnpu_device_memory_lifecycle`
- `package:inferrsi.ascend.skills.torchnpu_pinned_host_memory_lifecycle`
- `package:inferrsi.common.skills.training_input_pipeline`
- `package:inferrsi.common.skills.training_resource_budget`
- `package:inferrsi.ascend.skills.vllm_ascend`
- `package:inferrsi.common.skills.vllm_metal`
- `package:mlx.mlx.execution.cross_stream_dependency`
- `package:mlx.mlx.execution.evaluation_completion`
- `package:mlx.mlx.execution.post_detachment_buffer_lifetime`
- `package:sglang.common.llm.parallelism_and_extension`
- `package:sglang.common.llm.runtime_radix_hicache`
- `package:sglang.common.llm.tuning_and_validation`
- `package:sglang_omni.common.audio.serving_and_streaming_quality`
- `package:sglang_omni.common.omni.extension_lifecycle_validation`
- `package:sglang_omni.common.omni.pipeline_state_and_transport`
- `package:strata.common.llm.architecture_search_space`
- `package:strata.common.llm.controlled_execution_tuning`
- `package:strata.common.llm.engine_validation_contract`
- `package:vllm.common.llm.bounded_serving_measurement`
- `package:vllm.common.llm.extension_correctness_gates`
- `package:vllm.common.llm.runtime_and_kv_ownership`
- `package:vllm_omni.common.audio.streaming_serving_measurement`
- `package:vllm_omni.common.diffusion.measurement_and_profiling`
- `package:vllm_omni.common.diffusion.production_integration_gates`
- `package:vllm_omni.common.diffusion.step_state_and_output_validation`
- `package:vllm_omni.common.diffusion.upstream_review_gates`
- `package:vllm_omni.common.omni.stage_ownership_and_search`

### 37 entries

os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement

- `package:inferrsi.ascend.skills.ascend_device_health`
- `package:inferrsi.ascend.skills.ascend_video_diffusion_optimization`
- `package:inferrsi.common.skills.bound_windowed_attention_replay`
- `package:inferrsi.common.skills.budget_speculative_verification`
- `package:inferrsi.common.skills.kernel_writing_guide`
- `package:inferrsi.common.skills.model_sol_analysis`
- `package:inferrsi.common.skills.performance_ceiling_analysis`
- `package:inferrsi.ascend.skills.torch_npu`
- `package:inferrsi.common.skills.video_diffusion_optimization`
- `package:inferrsi.common.skills.weight_loading_optimization`
- `package:cache_dit.common.diffusion.residual_cache_calibration`
- `package:deepinfer.common.llm.bounded_windowed_replay`
- `package:deepinfer.common.llm.speculative_verification_budget`
- `package:deepinfer.common.llm.zero_overhead_deferred_scheduling`
- `package:diffusers.cuda.diffusion.group_offload_transfer_overlap`
- `package:flashattention.cuda.attention.generation_specific_dispatch`
- `package:flashinfer.cuda.llm.paged_decode_dispatch`
- `package:lmdeploy.cuda.llm.kv_quantization_capacity_cost`
- `package:pytorch.cuda.compiler.cudagraph_shapes_and_lifetimes`
- `package:qwen3_tts_engine.ascend.audio.codec_constants_and_state`
- `package:qwen3_tts_engine.ascend.audio.fixed_customvoice_prompt`
- `package:qwen3_tts_engine.ascend.audio.graph_batching_state_ownership`
- `package:sglang.cuda.llm.hierarchical_prefix_cache`
- `package:tensorrt_llm.cuda.llm.prefill_decode_disaggregation`
- `package:transformers.common.llm.kv_cache_strategy_contracts`
- `package:triton.common.kernel.bandwidth_fusion_resource_limits`
- `package:vllm_omni.ascend.diffusion.minimax_h3_reference_kv_reuse`
- `package:vllm_omni.ascend.diffusion.minimax_h3_sp_head_buckets`
- `package:vllm_omni.ascend.diffusion.qwen_image_21_eager_t2i`
- `package:vllm_omni.cuda.audio.concurrency_scaling_state_and_overlap`
- `package:vllm_omni.cuda.diffusion.minimax_h3_adaln_schedule_cache`
- `package:vllm_omni.cuda.diffusion.minimax_h3_cuda_mxfp8`
- `package:vllm_omni.cuda.diffusion.minimax_h3_fp32_modulation`
- `package:vllm_omni.cuda.diffusion.minimax_h3_qk_norm_rope`
- `package:vllm_omni.cuda.diffusion.minimax_h3_ref2va_teacache`
- `package:vllm_omni.cuda.diffusion.minimax_h3_vae_stacked_tiling`
- `package:xdit.cuda.diffusion.parallelism_freshness_and_topology`

### 2 entries

backend, hardware, os, model, phase, engine, engine_version, dependency_version, dtype, workload, quality, measurement

- `checkout:case.sarathi-chunk-budget`
- `checkout:case.sglang-gdn-source-contract`
