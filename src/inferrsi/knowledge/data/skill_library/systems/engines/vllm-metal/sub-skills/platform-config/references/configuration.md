# Configuration namespaces and syntax

The bundled helper adapts selected parsers in
[envs.py](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/envs.py).
It does not import that module, validate the complete engine or read environment
values. The two pass-through path/device-assignment variables are deliberately
excluded; user-provided paths are not captured in its output.

| Namespace | Contract | Common mistake |
| --- | --- | --- |
| Environment choices | Backend `mlx/mps`, MLX device `gpu/cpu`, multimodal `auto/multimodal-native/text-only`, image prefix `kernel/recompute`, TQ prefill `auto/0/1` | Case-sensitive strings; `GPU`, `vlm` and `AUTO` fail |
| Boolean environment switches | Literal `1` is true; every other supplied string is false; unset uses the source default | `true` or `yes` silently means off, not a parser failure |
| Spec ingest chunk | Integer >=0; 0 means one ingest forward; source default1024 | `1k` or negative values fail; block multiple is recommended, not parser-enforced |
| Ring base port | Integer1024..65535; engine separately checks base+pipeline-stages−1 | A valid base alone does not make a multi-stage port range valid |
| TQ prefill workspace | `auto` or nonnegative integer MiB; 0 disables materialization | A suffix such as `64MiB` is invalid; helper does not compute model-aware auto sizing |
| vLLM cache flags | `gpu_memory_utilization` is shared unified-memory budget; positive `kv_cache_memory_bytes` overrides cache sizing | Removed `VLLM_METAL_MEMORY_FRACTION` is not a supported override |
| `additional_config` | `turboquant`, `k_quant`, `v_quant`; MoE offload nested `moe_expert_offload:{cache_gb:number}` | TurboQuant is not enabled through a made-up env var or upstream heterogeneous KV dtype |

`MetalConfig.from_env()` takes device and multimodal choices. `get_config()`
caches that dataclass, while the `envs` module's individual variables are lazy
reads. `reset_config()` is relevant to a controlled test/config reload, not a
claim that changing a live server environment safely reconfigures workers.

Default TurboQuant fields are disabled, K `q8_0`, V `q3_0`. Once enabled,
K/V types are validated against their distinct source sets. Dense paged KV
must match model dtype (or `auto`); unsupported requested quantized KV is
rejected instead of pretending to save memory. TurboQuant's packed layout
and workspace are separate contracts. The numeric MoE cache field excludes
booleans and nonpositive values, but helper syntax success does not establish
that expert loading, quantization or a checkpoint is compatible.

An important source-versus-guide nuance: `VLLM_METAL_MM_PREFIX_PATH`'s registry
returns `None` when unset, while user guidance describes the effective kernel
default. The helper reports parser-level `null`, not a fabricated engine mode.
Likewise workspace sizing is model/scheduler-aware; do not turn a comment's
historical allowance into a fixed portable memory reserve.

Source [config dataclass](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/config.py),
[configuration guide](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/docs/configuration.md),
and [startup config checks](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/platform.py#L520-L830).
