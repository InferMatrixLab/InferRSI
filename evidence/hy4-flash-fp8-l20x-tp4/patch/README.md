# vLLM deployment

The selected source was pushed and verified on [codex/hy4-flash-h200-opt](https://github.com/fake0fan/vllm/tree/codex/hy4-flash-h200-opt). The branch name was specified in the original task. All results in this bundle were measured on four NVIDIA L20X devices. Use the tested local vLLM environment with matching generated CUDA extensions and the pinned ModelScope weights.

The measured deployment uses the following flags in addition to the model path, service name and loopback endpoint. Apply the selected revision's `examples/deployment/hy4-flash-options.json` extra flags last. For the eager-kernel stack these enable non-compiling CUDA providers and full decode CUDA graphs.

```bash
vllm serve "$MODEL_PATH" \
  --host 127.0.0.1 --served-model-name hy4-flash \
  --tensor-parallel-size 4 --max-num-batched-tokens 32768 \
  --max-num-seqs 1 --max-model-len 133120 \
  --no-enable-prefix-caching --seed 1024 \
  --attention-backend FLASHMLA_SPARSE --kv-cache-dtype auto \
  --speculative-config '{"method":"dfly","num_speculative_tokens":5}' \
  --reasoning-parser hy_v4 \
  --compilation-config '{"mode":"NONE","cudagraph_mode":"FULL_DECODE_ONLY"}'
```

For exact attempt binding, use the retained service-reuse adapter. Supply the local checkpoint and environment at runtime. Configure `TRITON_CACHE_DIR`, `VLLM_CACHE_ROOT`, `DG_JIT_CACHE_DIR` and `TORCHINDUCTOR_CACHE_DIR` on node-local storage consistently across launches.

## Signed-off commits

- Eager CUDA providers and full decode graphs. [4a076ad2e283](https://github.com/fake0fan/vllm/commit/4a076ad2e283331f23e6ccddb7cea0e3942fbbce)
- IndexPool rotation, Hadamard transform and quantization. [2c2c5e57dde1](https://github.com/fake0fan/vllm/commit/2c2c5e57dde150557badc7731439b47e66a795dd)
- Sliding-window logical indices. [560c5fdfe684](https://github.com/fake0fan/vllm/commit/560c5fdfe684496c1f7fb70e06b4905179758368)
- Small-group projection and gated pooling. [8a37987b1134](https://github.com/fake0fan/vllm/commit/8a37987b1134f147366fa09ba5567c86b1d35cfa)

The combined selected source passed all 14 CUDA kernel and indexing regression cases. All seven temporary experiment branches were archived and removed after the remote revision was verified.
