# Qwen3-Omni seed contract audit

Status: INCONCLUSIVE for the cause of observed WER variation. No demonstrated independent model correctness bug. Read-only audit of campaign source4645c450ba4ed036433a30dfcb9782f22b0c3bfd; no seed, model source, deployment, threshold or frozen protocol changes. No GPU work. The earlier seed-boundary-audit-v6.md is unchanged.

## Observed interface boundary

Standard chat request sampling fields are merged into the comprehension stage; other stages clone deployment defaults. See `vllm_omni/entrypoints/openai/serving_chat.py:1666`, `_build_sampling_params_list_from_request`, especially its explicit scope documentation. [Immutable campaign implementation](https://github.com/amy-why-3459/vllm-omni/blob/4645c450ba4ed036433a30dfcb9782f22b0c3bfd/vllm_omni/entrypoints/openai/serving_chat.py#L1666).

Talker deployment seed42 remains effective, including MRv2 base_config inheritance. The comment at `vllm_omni/deploy/qwen3_omni_moe.yaml:49–58` expresses speech-reproducibility intent but does not establish that residual predictor generators are connected. [Immutable configuration](https://github.com/amy-why-3459/vllm-omni/blob/4645c450ba4ed036433a30dfcb9782f22b0c3bfd/vllm_omni/deploy/qwen3_omni_moe.yaml#L49).

`vllm_omni/worker/sampling_utils.py:25` get_tts_local_seed explicitly reads only extra_args.tts_local_seed, not ordinary sampling_params.seed. The separate helper at32 can set both, but its existence alone does not prove a particular request route calls it. `tests/worker/test_tts_sampling_seed.py:13` explicitly tests separation of stage sampler seed and local MTP RNG: stage-only seed leaves the local seed None. [Helper](https://github.com/amy-why-3459/vllm-omni/blob/4645c450ba4ed036433a30dfcb9782f22b0c3bfd/vllm_omni/worker/sampling_utils.py#L25), [contract test](https://github.com/amy-why-3459/vllm-omni/blob/4645c450ba4ed036433a30dfcb9782f22b0c3bfd/tests/worker/test_tts_sampling_seed.py#L13).

Qwen3-Omni has no get_mtp_seed hook. MRv2 `worker_v2/model_states/omni_model_state.py:1372` resolves missing hook to None; V1 `worker/gpu_model_runner.py:2060` directly reads tts_local_seed and otherwise returns None. Neither ordinary stage seed42 nor native benchmark dataset seed alone establishes per-request residual RNG. [MRv2](https://github.com/amy-why-3459/vllm-omni/blob/4645c450ba4ed036433a30dfcb9782f22b0c3bfd/vllm_omni/worker_v2/model_states/omni_model_state.py#L1356), [V1](https://github.com/amy-why-3459/vllm-omni/blob/4645c450ba4ed036433a30dfcb9782f22b0c3bfd/vllm_omni/worker/gpu_model_runner.py#L2060).

## Qwen3-TTS is an explicitly connected, different route

Local git blame attributes Qwen3-TTS `get_mtp_seed = staticmethod(get_tts_local_seed)` to upstream commit a9e2117f5e18a882332501a3d96c6eaa076a9310, “[Core][Model] Enable Qwen3-TTS MRV2 and optimize the TTS pipeline (#7781)”. [Official immutable source](https://github.com/vllm-project/vllm-omni/blob/a9e2117f5e18a882332501a3d96c6eaa076a9310/vllm_omni/model_executor/models/qwen3_tts/qwen3_tts_talker.py).

At campaign revision, Qwen3-TTS speech adapter `entrypoints/openai/tts_adapters/qwen3_tts.py:733` explicitly propagates its deploy stage seed into tts_local_seed with setdefault. The associated test `tests/entrypoints/openai_api/test_serving_speech.py:5706` verifies default-seed propagation. These are Qwen3-TTS speech-route facts, not a universal promise for Qwen3-Omni chat. [Adapter](https://github.com/amy-why-3459/vllm-omni/blob/4645c450ba4ed036433a30dfcb9782f22b0c3bfd/vllm_omni/entrypoints/openai/tts_adapters/qwen3_tts.py#L733), [test](https://github.com/amy-why-3459/vllm-omni/blob/4645c450ba4ed036433a30dfcb9782f22b0c3bfd/tests/entrypoints/openai_api/test_serving_speech.py#L5706).

## Conclusion and possible future clarification

The audited source/tests do not establish a contract that a standard Qwen3-Omni chat request seed governs all residual predictor draws. The YAML reproducibility wording warrants clarification against actual wiring, but stochastic WER differences alone do not prove a model bug or identify their cause. No historical baseline should be selected/recomputed to improve a verdict.

If a future explicit Omni residual-seed contract is agreed, a minimal independent change could expose get_tts_local_seed through the Qwen3-Omni model hook and test explicit tts_local_seed across V1/MRv2, batch permutations, request slot reuse and generator cleanup. Whether ordinary request.seed should propagate to Talker is a separate API decision; it must not be changed implicitly or mixed into frozen comparisons. Native numeric scheduling and finite-precision effects can still prevent bitwise end-to-end reproducibility. No implementation or GPU validation was performed here.
