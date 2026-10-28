# Source scripts and support

| Source artifact | Decision / owner | Reason / replacement |
| --- | --- | --- |
| vllm_metal/envs.py parser logic | adapt / platform-config | selected explicit-input syntax checker avoids ambient/private data and native imports |
| vllm_metal/v1/kv_offload/config.py + cache_policy.py arithmetic | adapt / cache-lifecycle | narrow dense uniform pool ledger; omitted probes, allocator/layout/native actions explicit |
| tools/avg_gen_length.py | adapt / qualification | safe token summary idea retained; network dataset, engine/model/MLX and measurement removed |
| tools/native_sampling_probe.py | reference-only / qualification | sends HTTP requests against a running engine; language-range heuristic is not a universal corruption oracle |
| tools/speculative_parity.py, GQA/NAX/native sampling/benchmark tools | unselected / qualification | source tool-name inventory only where not in readset; no claim of complete inspection; native runtime/model requirements unavailable |
| scripts/test.sh, scripts/lint.sh | exclude execution / platform-config | can install tools, invoke setup/toolchain, build artifacts or broad native suite; pure selected tests run explicitly instead |

Every runnable helper is linked from its owning SKILL.md. Upstream paths are provenance, not runtime checkout dependencies.
