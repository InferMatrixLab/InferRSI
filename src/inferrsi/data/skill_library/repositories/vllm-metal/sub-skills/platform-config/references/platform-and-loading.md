# Platform and model-loading contracts

## Preparation without conflating an import with a device

At this snapshot, Python support is `>=3.12,<3.14`; public execution requires
Apple Silicon and macOS 15+. Package metadata pins MLX exactly to 0.32.4 because
the native extension uses MLX private headers and its dylib has no versioned
ABI promise. It also pins an mlx-lm Git revision and mlx-vlm 0.7.6. These are
source-snapshot facts, not portable dependency recommendations for newer heads.

Stable installation is through the project's Homebrew tap/formula. A source
development setup is materially different: full Xcode/SDK 26.2+, installer,
native launcher/shader builds and development dependencies. Inspect and obtain
authority before any of those effects. Do not pipe an installer into a shell
as a diagnostic shortcut. The release wheel carries prebuilt launchers and
shaders; a source checkout without those bytes is not equivalent.

After an authorized installation, safe read-only identity checks are:

```bash
python -I -c 'import importlib.metadata as m; import vllm_metal; print(m.version("vllm-metal"), vllm_metal.__version__)'
python -I -c 'from vllm_metal.config import MetalConfig; print(MetalConfig.from_env())'
```

The root is deliberately lazy. These checks can succeed without vLLM, MLX,
weights or native operators. Plugin entry points are `vllm.platform_plugins`
`metal → vllm_metal:register` and `vllm.general_plugins`
`gguf_metal → vllm_metal.gguf.vllm_integration:register`. Actual registration
adds environment parsers, applies compatibility patches, then asks platform
availability. It is not just importing `vllm_metal`.

On macOS registration defaults multiprocessing to `spawn` only if the user
did not explicitly set a value, avoiding an Objective-C-initialized fork.
An explicit `fork` value remains authoritative and potentially unsafe.
MLX command-buffer op defaults similarly use `setdefault`; memory-buffer
policy belongs to the engine configuration, not the root import.

## Select a backend, then its supported contracts

MLX is default. `VLLM_METAL_BACKEND=mps` opts into PyTorch MPS, defaults
`VLLM_USE_V2_MODEL_RUNNER=1` and `VLLM_USE_HW_AGNOSTIC=1`, and requires
`PYTORCH_ENABLE_MPS_FALLBACK=0` during MPS runs so silent CPU fallback is not
misreported as MPS execution. Its documented path uses unquantized FP16/BF16,
greedy requests; output-token logprobs are supported, prompt logprobs and
explicit token-ID scoring are not. Do not infer that every MLX feature is MPS
supported. Upstream model/layer hooks are preferred over copying model blocks.

The MLX path rejects an explicit V2 runner. Executor `auto`/unset resolves to
`uni` for one pipeline stage, `mp` for multiple. Explicit `uni` plus multiple
stages fails rather than silently changing topology. Tensor parallelism is
rejected; pipeline support does not imply TP or a qualified multi-host run.

## Keep effective multimodal selection stable

`auto` permits source-defined compatibility fallbacks; `text-only` forces a
text backbone; `multimodal-native` disables those overrides for deliberate
validation. GGUF is text-only. Gemma 4 may use a vision sidecar when matching
vision weights, a loadable processor and no speculative configuration permit
it; otherwise text-only with a reason. Some FP8 Qwen wrappers use the text
backbone because their vision loader does not sanitize scale tensors. Neither
an architecture label nor text success establishes image support.

`GenerationLoadRequest.from_runner` re-derives the effective route. An API
configuration retaining multimodal state while the worker selects text-only
is an error: checkpoint/mode changed, so restart with stable identities.
Pipeline loading remains lazy until owned layers are known; custom GGUF/AWQ
loading cannot be assumed to implement that same contract. Per-layer KV/head/
window metadata is not stage-sliced and is explicitly rejected with PP.

## Source evidence

Pinned [package metadata](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/pyproject.toml),
[root registration](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/__init__.py),
[platform policy](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/platform.py#L520-L830),
[load request and metadata](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/v1/model_lifecycle.py),
[MPS contract](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/docs/pytorch-mps.md),
and [native build identity](https://github.com/vllm-project/vllm-metal/blob/e7df7a6ff215f99c7842552d230fdbc709835934/vllm_metal/metal/build.py#L1-L160).
These source links identify provenance, not runtime checkout dependencies.
