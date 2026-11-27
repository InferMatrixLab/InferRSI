# Training, evaluation, data and precision

## A controlled module update

Inputs: registered model parameters/buffers, a tiny batch/target schema,
loss/reduction, optimizer groups, device and numerical mode. Output: a finite
loss, expected gradients, intended parameter update and restorable state.

1. Register trainable values as `nn.Parameter`, nested layers as modules or
   ModuleList/ModuleDict and nonlearnable state with `register_buffer`.
   Persistent buffers appear in `state_dict`; nonpersistent buffers still move
   with `.to()` but are not serialized. Plain Python tensor attributes are not
   automatically registered state.
2. Move/initialize the model on the intended device before constructing the
   optimizer. Confirm optimizer groups contain the intended live Parameters;
   record per-group learning rates, weight decay and frozen parameters.
3. Start with one eager batch and `num_workers=0`. Check dimensions, integer
   versus floating labels, padding/masks and loss reduction. Call `model(x)`
   through Module hooks, not `model.forward(x)` directly.
4. Set `train()`, clear gradients at the intended boundary, run forward/loss,
   `loss.backward()`, inspect finite gradients, then `optimizer.step()`.
   `zero_grad(set_to_none=True)` preserves absent gradients as None: optimizers
   can skip a parameter with no gradient, which differs from a zero gradient.
5. Step a scheduler at its documented update boundary; account for optimizer
   steps skipped by mixed-precision overflow rather than blindly advancing time.
6. For validation call `eval()` and choose `no_grad()`/`inference_mode()` based
   on later tensor use. Restore training mode after evaluation if continuing.
7. Save model/optimizer/scheduler/scaler/RNG and data-progress state for resume
   as appropriate; loading only weights does not resume optimization history.
   Use the distributed/checkpoint route for trust and storage details.

Run the bundled [tiny update](../scripts/tiny_training.py) with `--steps 2`
for an in-memory CPU diagnostic. It does not download a dataset or qualify a
model's convergence. Compare state before/after, not loss monotonicity from two
random batches. Treat `nn` architecture families (conv, recurrent, transformer,
losses, embedding) as model-specific shape and state contracts under this route.

## DataLoader workflow

1. A map-style Dataset owns indexing/length; a sampler chooses indices.
   An IterableDataset owns traversal and must shard itself across worker/rank
   replicas. Default loader length can be an estimate for iterable datasets.
2. Validate one sample and one collated batch before enabling concurrency.
   Default collation stacks compatible tensors; variable-length samples need
   an explicit padding/list/ragged policy and matching loss mask.
3. Choose sampler or shuffle deliberately; batch_sampler is mutually exclusive
   with batch_size/shuffle/sampler/drop_last. With a distributed sampler, each
   epoch's ordering needs the sampler's `set_epoch(epoch)` when shuffling.
4. Increase workers only after correctness. At num_workers=0, leave
   prefetch_factor=None and persistent_workers=False; these multiprocessing
   controls are rejected otherwise. With workers, prefetched batch residency
   grows roughly with workers times prefetch_factor and batch footprint.
5. Under spawn (notably Windows), put process launch in a main guard and use
   picklable top-level worker/collate callables. Avoid CUDA allocations in loader
   workers; return host batches and transfer in the consumer.
6. Seed the loader generator and other worker RNGs consistently. Persistent
   workers retain dataset state across epochs; explicit reset/sharding matters.
   `in_order=False` can skew imbalanced training and reproducibility.
7. Pinning and `non_blocking=True` can help transfer overlap only with correct
   source lifetime and stream dependencies. Measure the whole input pipeline,
   including host memory, before increasing worker count or pinned residency.

## AMP and accumulation

Choose a device-supported dtype after checking numerical sensitivity. Keep
model parameters in the intended master precision; autocast chooses per-op
execution dtype in the forward/loss region. Backward outside autocast follows
the forward choices. A CUDA FP16 pattern is:

```python
scaler = torch.amp.GradScaler("cuda")
optimizer.zero_grad(set_to_none=True)
for micro_x, micro_y in micro_batches:
    with torch.autocast("cuda", dtype=torch.float16):
        loss = loss_fn(model(micro_x), micro_y) / len(micro_batches)
    scaler.scale(loss).backward()
scaler.unscale_(optimizer)  # once after the full effective batch
torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm)
scaler.step(optimizer)
scaler.update()
```

This is a complete accumulation window; handle a final shorter window with its
actual normalization. Never combine scaled and already-unscaled gradients.
Call unscale_ once per optimizer per step, then clip; update the scale only at
the effective-batch boundary. BF16 and CPU autocast have different scaling and
operator-support needs; do not force this CUDA FP16 recipe onto every device.
Record skipped steps/nonfinite values separately from loss quality.

## Activation recomputation and SDPA

`torch.utils.checkpoint.checkpoint(fn, *args, use_reentrant=False)` trades
saved activations for recomputation. Pass use_reentrant explicitly. The backward
invocation must be equivalent to forward: global state, RNG policy and device
movement can invalidate that. Compare gradients with the uncheckpointed control;
then measure peak memory and full step time. It is distinct from disk checkpointing.

For `scaled_dot_product_attention`, record Q/K/V batch/head/sequence/head-dim,
strides/dtype/device, mask semantics, causal alignment, dropout and GQA policy.
Boolean **True means attend** in SDPA; MultiheadAttention key_padding_mask uses
True for masked positions. Pass dropout_p=0.0 explicitly for evaluation.
Do not combine attn_mask and is_causal when the installed contract rejects it.
GQA head divisibility and kernel/layout support need separate qualification.

CUDA SDPA selection checks enabled backends and actual runtime eligibility,
including Flash, memory-efficient, cuDNN and math paths. The C++ selector iterates
a computed priority order and validates can_use predicates; it is not a fixed
three-backend list inferred from a high-level docstring. Force one candidate
with `torch.nn.attention.sdpa_kernel` to obtain rejection diagnostics, retain
the math control, compare outputs and gradients, then measure the actual kernel.
Runtime cuDNN/architecture/shape guards can reject a seemingly supported dtype.

## Compression branch

Quantization/pruning/parametrization require a numerical baseline and target
backend. This snapshot's quantization documentation directs new quantization
development to torchao and migration from eager/FX/PT2E paths; it retains legacy
public APIs and an outdated planned deletion date. Treat that as migration
guidance, not proof APIs are absent. Inspect the installed namespace before
changing a saved quantized model. External torchao algorithms/checkpoint formats
are outside this repository's execution evidence; pin and qualify them separately.


Source support at the pinned revision (exact inspected spans and byte digests are in the root [readset](../../../references/source-readset.json)):

- [`torch/utils/data/dataloader.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/utils/data/dataloader.py)
- [`docs/source/notes/modules.md`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/docs/source/notes/modules.md)
- [`docs/source/notes/amp_examples.md`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/docs/source/notes/amp_examples.md)
- [`torch/utils/checkpoint.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/utils/checkpoint.py)
- [`torch/nn/functional.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/nn/functional.py)
- [`aten/src/ATen/native/transformers/cuda/sdp_utils.cpp`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/aten/src/ATen/native/transformers/cuda/sdp_utils.cpp)
- [`docs/source/quantization.md`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/docs/source/quantization.md)
- [`torch/optim/optimizer.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/torch/optim/optimizer.py)
