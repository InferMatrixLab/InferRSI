# Precision and training procedure

## Establish a controlled baseline

Move the model and every input to the selected device; create the optimizer
after the final parameter placement when that avoids stale parameter ownership.
Use tiny fixed data with a trusted FP32 reference and an explicitly chosen
tolerance. Retain model state, optimizer state, RNG and update count. Compare
forward loss, representative gradients and parameter deltas. Do not infer
training quality or convergence from successful device allocation or a decreasing single loss.

## Autocast and scaling

`torch.autocast("npu", dtype=...)` controls operator policy rather than converting
the whole model. The legacy `torch.npu.amp.autocast` wrapper delegates to that
device-type API. The inspected C++ AutocastPrivateUse1 registration uses
lower-precision, FP32 and promotion policy groups and explicitly bans
`binary_cross_entropy`/BCELoss under autocast, suggesting logits-based loss.
Actual dtype support depends on the hardware/runtime/operator (F18).

```python
scaler = torch.npu.amp.GradScaler()
optimizer.zero_grad(set_to_none=True)
with torch.autocast("npu", dtype=torch.float16):
    loss = loss_fn(model(inputs), targets)
scaler.scale(loss).backward()
scaler.unscale_(optimizer)
torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
scaler.step(optimizer)
scaler.update()
```

The illustrated clipping threshold is an example, not a repository acceptance
bar. Pick workload-specific tolerances/limits before comparing candidates.
Unscale before clipping. `unscale_` is once per optimizer per step after all
accumulation. Do not unscale
twice or call scale update for each microbatch of one accumulated update.
With multiple optimizers, preserve each optimizer's state and the intended
single iteration scale-update schedule. Confirm installed API behavior before
adapting advanced patterns.

TorchNPU's scaler tracks dynamic/static modes, per-optimizer states and device
overflow. It disables itself with a warning when NPU AMP is unavailable;
`is_enabled()` must therefore be observed rather than assumed. The unscale path
groups gradients by device/dtype, handles fused combined buffers and sparse
values, invokes nonfinite check/unscale and synchronizes distributed overflow
state (F19). A skipped update is not automatically a failed kernel; capture
finite/overflow state, scale before/after and actual parameter mutation.

For custom autograd functions use `torch.amp.custom_fwd(..., device_type="npu")`
and `custom_bwd(..., device_type="npu")` where compatible; legacy wrappers are
deprecated at this pin. Define the gradient math independently of autocast.

## Optimizer, migration and persistence

TorchNPU exposes fused Adam/AdamW/SGD/Lamb/RMSprop families and other variants.
Switch one optimizer at a time and preserve hyperparameters, parameter groups,
state dtype, sparse support and accumulation. Their names are not proof of
equivalence to every upstream optimizer configuration; fused-buffer behavior
also interacts with GradScaler.

For checkpoint portability prefer a state-dict boundary and explicit target
placement. Validate loaded parameter/optimizer/scaler/RNG state and resumed
update behavior. Async save and custom storage formats have extra lifetime
contracts; copying NPU tensors to CPU is not proof an asynchronous writer has
finished. [Support workflows](../../../references/support-workflows.md) names
the inspected serialization boundary and the uninspected async-save details.

The broad `transfer_to_npu` migration shim changes process-wide APIs and CUDA
device arguments. Use it only when explicitly selected, in a clean process,
and compare the exact model operations. It cannot port CUDA kernels, certify
all third-party packages or replace numerical validation.
