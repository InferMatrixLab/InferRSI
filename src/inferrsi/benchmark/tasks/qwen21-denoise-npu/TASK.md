# Qwen-Image 2.1 single-stream denoising task

Optimize a complete prefill-and-denoise request on one Ascend NPU. Implement
`compute(latents, text, text_mask, sigmas, positions, params, *, config)` and
return every updated latent as one tensor of shape
`[len(sigmas)-1, batch, height*width, channels]`.

The source architecture is Qwen-Image **2.1**, with a single joint text/image
stream, prefix K/V reuse and one shared modulation projection. The task uses
scaled dimensions, random BF16 weights and already embedded text. It requires
PyTorch and the configured torch_npu/CANN runtime. Its Python entry can run
directly from a copied task directory. A model checkpoint download is unnecessary.

## Computation

The fixed task and cases are in `task.json`. Parameter dictionary construction
and exact tensor shapes are in `workload.py`. All tensors are read-only.

1. Normalize text using zero-centered RMSNorm, project, apply approximate-tanh
   GELU and project into the model width. Project noisy image latents separately.
2. Generate sinusoidal timestep features with time factor 1000, project through
   SiLU and project again. Append a zero-timestep conditioning row. A shared
   SiLU-plus-linear produces attention scale/gate and MLP scale/gate.
3. On the first step, run the joint sequence `[prefix, target]`. Prefix queries
   attend valid prefix keys. Target queries attend valid prefix and all target
   keys. Prefix modulation uses timestep zero, target modulation the current
   sigma cast to the running dtype. Padded text keys remain masked.
4. Each block applies affine-free LayerNorm and scale, fused QKV projection,
   learned Q/K RMSNorm, three-axis interleaved-pair RoPE, attention, output
   projection and tanh-gated residual. The second sublayer applies LayerNorm,
   scale, separate gate/up projections, SwiGLU, down projection and gated residual.
5. Preserve each block's first-step prefix K/V. Later steps compute target queries
   and target K/V, then prepend that block's cached prefix K/V. The original
   baseline already has this reuse.
6. Apply scale-only adaptive final LayerNorm, project to latent channels, and
   update with FP32 Euler arithmetic, `x + (next_sigma-sigma)*prediction`, cast
   back to the running dtype. Repeat the entire supplied sigma sequence.

The score cases use the historical eight-step Turbo sigma grid and terminal zero.
Small validation cases cover another schedule, a different head dimension,
batch size two, padded text keys and an immediate in-place weight update.

## Allowed changes

Change the candidate's scheduling, layouts, projections, pointwise operations,
attention implementation and request-local reuse. Existing configured PyTorch,
torch_npu and custom NPU kernels may be used. Examples of search directions
include static conditioning/modulation reuse, gate/up fusion, normalization and
RoPE kernels, intermediate allocation and host dispatch reduction.

Every request includes all input-dependent preparation, prefix work, cache
construction, all denoising steps, scheduler updates and trajectory production
inside `compute`. Persistent compiled kernels and weight-only preparation require
correct invalidation after parameter changes. Input-dependent state is local to
one invocation. Keep every supplied step, token, text key mask and output.

Candidates execute as reviewed trusted code. Follow the stated mathematical
contract, including the numerical tolerance in `task.json`. Read task inputs and
parameters through the entry arguments. Accessing reference code, evaluation
seeds or private expected outputs during candidate execution violates the task.
Editing shared modules, monkeypatching the reference, modifying inputs or using
cached latent outputs also violates the task. The import guard enforces the
standalone dependency requirement for vllm, vllm_omni, diffusers and transformers.

## Run

For a complete RSI optimization benchmark in the current Agent conversation,
start a session with `inferrsi benchmarks session start qwen21-denoise-npu`.
Supply its session directory, round and time budgets, condition label, allocator
prefix and sampling arguments. The command returns the frozen task and editable
candidate paths. Use `session knowledge` for permitted RSI context, then repeat
`session round` with the changed candidate and hypothesis. Read each independent
observation before the next change. Complete the frozen round budget and use
`session final` to independently retest the selected source. Report the generated
`summary.json`, including failures and available usage exports. The following
direct command evaluates one candidate inside that optimization workflow.

Use the existing allocator in the prepared NPU environment. Copy this directory
and a reviewed candidate file into an independent workspace. For example, from
the copied task directory, with `candidate.py` initially copied from `baseline.py`,
run the following command.

```bash
npu run --gpus 1 --timeout 18m --wait 30m -- \
  python benchmark.py --candidate candidate.py --output-dir outputs/round-01 \
  --pairs 2 --samples 3 --warmups 1
```

Each output directory must be new. The caller controls the allocation, process
deadline, iteration budget and final selection. The same entry can be invoked
through the existing InferRSI external-command scenario. Choose a new output
directory for every invocation. `--case compact` selects a partial qualification,
which the result labels `score_scope=selected_cases`. A complete task score
requires all three measured cases and the validation cases.

Use `--case smoke --device cpu --check-only` for a small mathematical check in a
prepared PyTorch CPU environment. CPU mode requires `--check-only`. Normal task
execution targets the allocated logical device `npu:0`.

The entry freezes task, candidate and evaluator source with SHA256. It checks all
steps against an independent FP32 CPU reference that recomputes the full joint
sequence at every step and explicitly evaluates attention probabilities. Input
and parameter preservation are checked outside the timed region. Both methods
receive separate storage with equal values. Each timed request has fresh latent
and text values. Weights remain stable for a case, followed by an immediately
repeated same-storage update check.

Paired blocks alternate baseline/candidate order. Each implementation pays its
own warmup. Synchronization brackets the complete request, so Python dispatch,
all eight steps and final output completion enter timing. Oracle preparation
and validation are outside the score. Retain their wall-clock cost separately.
Per-case speedup is baseline median / candidate median. The task aggregate is
the geometric mean of measured case ratios. Compare absolute case latencies
alongside speedups when runs occur at different times.

`result.json` retains calls, step errors, samples, case metrics, import checks and
failure phase. `identity.json` and `snapshot/` identify the actual code evaluated.
Exit codes are 0 for completion, 2 for candidate failure and 1 for infrastructure
or baseline failure. Candidate import/execution consumes an attempt. A failure
keeps its evidence and has no valid speed score. The caller must collect process
termination and allocation-release evidence when cancelling or timing out a run.

## Scope

This task measures a scaled denoiser with synthetic weights and conditioning.
It preserves the source's single-stream blocks and prefill/decode dependencies.
It covers latent numerical correctness and whole-denoiser latency. Image
generation quality, the text encoder, VAE, checkpoint loading, HTTP serving and
multi-device sequence parallelism require separate workloads.

Source derivation, historical optimization evidence and licensing are recorded
in `NOTICE.md`. Current task verification is recorded in the delivery's validation
report and is independent of historical model performance results.
