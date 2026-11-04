# FlashInfer engineering attempts: actual outcomes

Historical launch snapshot before GPU2076. See e2e-observation-2076.md for the subsequent actual result and integration decision.

Candidate 8859ef319486eb5ed4a444fc66c1018cbebbab33; Issue67; 2026-10-23. INCONCLUSIVE for model quality and service performance.

Job2041 (v3) exited1 before the first operator result: selected runtime had ninja installed but wrapper PATH omitted its bin directory. The preceding pending/estimated-start observation is superseded. Raw log starts02:43:41UTC; exit-file mtime02:43:55UTC. The scheduler record expired before final capture, so this is an approximately14-second log window, not certified allocated duration. Reserve its full1800-second limit in the budget. No HTTP requests or measured performance results exist.

Job2074 (v4) FAILED1:0 with scheduler RunTime11seconds, oneGPU, released. Adding runtimebin resolved ninja; the installed FlashInfer C++ path then invoked bare nvcc, absent from PATH. It also selected a default TensorRT-LLM cache outside the required task root. No GEMM output/model/HTTP result was produced. The fallback-directory violation is preserved; no later run is allowed to reuse it. This is an environment failure, not measured kernel regression.

Prospectivev5 supplies CUDA_HOME, explicit TRTLLM_DG_NVCC_COMPILER and root-contained TRTLLM_DG_CACHE_DIR/DG_JIT_CACHE_DIR; it restores the already verified abstract VLLM IPC endpoint. Engine/operator/HTTP bytes are unchanged. Independent review caught a v4 EXIT trap that could replace the original exit on scheduler-query failure; v5 uses best-effort scheduler capture and explicit original exit. A trap-time RUNNING snapshot is not final completion evidence. v5 is not yet executed in this record.

Budget: prior2388 + conservative2041reserve1800 + actual2074elapsed11 =4199 of7200 readiness GPU-seconds committed. A prospective1800-second retry remains within this phase cap. Initial147seconds remain separately recorded. No service gain, final quality, or parity is claimed.
