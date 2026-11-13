# Source attribution and task derivation

The independently written task follows these Apache-2.0 source contracts.

- Qwen-Image 2.1 original transformer, including single-stream blocks, separate
  gate/up projections, zero-centered text RMSNorm, scale-only final adaLN,
  interleaved complex-pair RoPE and existing prefix K/V reuse. The source header
  attributes the implementation to vLLM-Omni contributors and its Diffusers
  adaptation. [Original transformer](https://github.com/vllm-project/vllm-omni/blob/f69b1f2b19cece03f6736c7da093ea25de0e24fd/vllm_omni/diffusion/models/qwen_image_21/qwen_image_21_transformer.py)
- Original pipeline entry and denoising structure. This task receives embedded
  text and latent tokens and implements deterministic Euler updates directly.
  [Original pipeline](https://github.com/vllm-project/vllm-omni/blob/f69b1f2b19cece03f6736c7da093ea25de0e24fd/vllm_omni/diffusion/models/qwen_image_21/pipeline_qwen_image_21.py)
- The later conditioning/shared-modulation optimization provides evidence that
  static work and pointwise launches matter for this model. The task baseline
  follows the earlier source. [Optimization source](https://github.com/vllm-project/vllm-omni/commit/b164fea797531c1fa10f8b87829632cad006b9fc)

The historical InferRSI Qwen-Image 2.1 Turbo experiment used complete model image
generation and evaluated decoded outputs. Its numerical results concern that
campaign and its hardware. The present task's smaller random network has an
independent validation and timing protocol. [Historical acceptance](https://github.com/InferMatrixLab/InferRSI/issues/3)

For the task baseline, PyTorch linear operations replace engine parallel-linear
wrappers and PyTorch SDPA replaces the engine attention dispatcher. Prefill
still computes the joint text/image sequence, with the same block-causal
dependency and native prefix K/V reuse. Later decode calls operate on the target
tokens. The task keeps repeated text projection, timestep-zero modulation,
per-block per-token modulation expansion, eager pairwise RoPE, separate MLP
gate/up projections and Euler-loop dispatch available for optimization.

Weights, dimensions, token layouts and conditioning inputs are synthetic. The
learned text encoder, checkpoint, VAE, service runtime, graph manager, quantized
prefix cache, offload and distributed execution are outside this task. All code
needed by the task is in this directory and uses ordinary PyTorch plus the
configured device runtime. Source URLs provide provenance, and runtime imports
of either engine are blocked by the evaluator.

Copyright contributors to the vLLM-Omni project for the attributed source
architecture and expressions. Copyright InferRSI contributors for the task,
reference implementation, workload and evaluator. Distributed under Apache-2.0,
with the accompanying LICENSE.
