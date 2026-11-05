# Norm / QKV fusion candidate audit

Read-only CPU/source analysis; UNTESTED candidate, no engine/GPU change.

**Finding: native IR priority is intentional for Inductor, not evidence of unfused execution.** Installed files were byte-compared with official vLLM revision5df63a7203cdb9328d824a27b682e77c7b9928be for cuda.py, IR layernorm.py, vllm_c.py, config/kernel.py and qk_norm_rope_fusion.py; all match.

[CUDA platform714–718](https://github.com/vllm-project/vllm/blob/5df63a7203cdb9328d824a27b682e77c7b9928be/vllm/platforms/cuda.py#L714) explicitly chooses native when backend=inductor and compilation enabled, otherwise vllm_c then native. [IR norm10–63](https://github.com/vllm-project/vllm/blob/5df63a7203cdb9328d824a27b682e77c7b9928be/vllm/ir/ops/layernorm.py#L10) is ordinary tensor arithmetic with FP32 reduction and defined dtype transitions. Thus compiler can fuse these expressions; provider label is not a GPU kernel label.

Actual completed C1 trace summary supplies stronger evidence: stage0 contains `triton_red_fused_fused_add_rms_norm_moe_forward_0`6048 events, `triton_red_fused_fused_add_rms_norm_1`5544, and `triton_poi_fused_clone_index_rms_norm_split_split_with_sizes_view_3`5922. These names establish compiled fusion exists, not that every named operation executes as a separate component or that fusion is globally optimal. Stage1 includes long `triton_per_fused_...mean_mul_neg_pow_rsqrt...` kernels25200 times, consistent with predictor attention block footprint. Names alone cannot assign each norm to Talker versus predictor or quantify removable traffic. Need generated-code/source-map correlation and actual-shape timing before proposing a replacement.

## Existing alternatives and configuration

[IR priority configuration](https://github.com/vllm-project/vllm/blob/5df63a7203cdb9328d824a27b682e77c7b9928be/vllm/config/kernel.py#L21) supports `kernel_config.ir_op_priority.rms_norm` and `.fused_add_rms_norm` lists. Existing [vllm_c providers](https://github.com/vllm-project/vllm/blob/5df63a7203cdb9328d824a27b682e77c7b9928be/vllm/kernels/vllm_c.py#L23) call native CUDA custom kernels, including fused residual-add norm. This is an existing implementation to benchmark, not a new kernel to invent. Replacing an Inductor-decomposable expression with opaque custom kernels can break surrounding fusion or add copies, so `vllm_c` is not presumed faster.

No generic `flashinfer` or named `triton` RMSNorm provider is registered in this pinned installation. FlashInfer integrations found are specialized norm+quant/allreduce paths; NVFP4 quantization is outside current BF16 arithmetic contract, and TP1 offers no tensor-parallel allreduce to remove. Oink provider requires capability100 plus external registered ops, so it is not an applicable cc90 toggle. Inductor-generated Triton norm kernels already exist despite the provider name native.

Existing [QK norm+RoPE fusion pass](https://github.com/vllm-project/vllm/blob/5df63a7203cdb9328d824a27b682e77c7b9928be/vllm/compilation/passes/fusion/qk_norm_rope_fusion.py#L197) uses `_C.fused_qk_norm_rope`; compilation pass control is `enable_qk_norm_rope_fusion`. It is a candidate only if the actual model graph matches supported head/layout patterns and the pass is not already applied. This audit does not establish runtime match status. A fused RoPE+KV update flag also exists but platform gating excludes CUDA for that particular implementation; do not blindly enable similarly named knobs.

## Predictor already has custom arithmetic and packing

[Campaign4645 predictor](https://github.com/amy-why-3459/vllm-omni/blob/4645c450ba4ed036433a30dfcb9782f22b0c3bfd/vllm_omni/model_executor/models/common/qwen3_code_predictor.py#L48): custom `_RMSNorm` uses FP32 mean/pow/rsqrt, casts before multiplying weight, and intentionally avoids generic fused norm for numeric sensitivity. It does not use vLLM IR RMSNorm, so changing IR priority will not directly replace it. Its full body uses torch.compile(epilogue_fusion=False); this option does not disable all Inductor fusion, as trace kernels confirm.

Q/K/V are already packed into one nn.Linear (197,288–292); gate/up projection is already packed (378). `_split_qkv`219 materializes dense K/V contiguous copies deliberately to preserve SDPA layout. A hypothetical packed-layout attention kernel could avoid those copies and fuse Q/K norm+RoPE, but it changes layout, reduction order and kernel shape, and requires actual tensor parity/quality before any speed claim. Reimplementing generic QKV packing duplicates existing work.

## Bounded next candidate

First inspect generated code for the high-count predictor fused kernels to determine whether dense K/V materialization remains an actual standalone read/write and whether reduction/elementwise kernels can be combined while preserving cast points. If yes, a predictor-specific norm+RoPE+layout operation could remove materialization/launches; applicability and gain remain unknown. In parallel, existing vllm_c priority or QK norm+RoPE pass can be investigated on backbone-only actual shapes, but only after confirming their current activation and exposed cost. No numeric speedup, source-level bottleneck certainty, or quality qualification follows from this audit.
