# Model-weight residency is a separate lifetime

## Executing path and owners

**CODE.** A KSampler node delegates to `common_ksampler`, then
`comfy.sample.sample` and `comfy.samplers.KSampler.sample`
([node entry](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/nodes.py#L1581-L1633),
[sample entry](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy/sample.py#L79-L84),
[sampler dispatch](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy/samplers.py#L1443-L1463)).
`CFGGuider.outer_sample` prepares sampling before invoking the denoiser.
`_prepare_sampling` gathers additional models and estimates required/minimum
memory before `load_models_gpu`
([outer sample](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy/samplers.py#L1240-L1274),
[estimate and load](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy/sampler_helpers.py#L165-L214)).
Estimates choose policy; they are not measurements proving that a workload fits.

| Owner | State / lifetime | Important distinction |
|---|---|---|
| PromptExecutor output cache | Entries may hold model-producing outputs | Evicting an entry does not prove all references or device allocations are released |
| ExecutionList | Consumer references and output-link callbacks for this prompt | A live consumer can retain an entry after a retention-policy decision |
| PromptModelTracker | Dynamic models seen on the current prompt's output links | `start/add/end` controls current-prompt pin policy; end clears flags and tracker references |
| LoadedModel registry | Managed wrappers, device and use flags; weak model references | Registry membership is not equal to full device residency |
| ModelPatcher | Model, patch identity/backups, load/offload devices and loaded-byte bookkeeping | Static and dynamic implementations have different physical-memory paths |

Ownership evidence:
[`ExecutionList`](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy_execution/graph.py#L222-L264),
[`PromptModelTracker`](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy/model_patcher.py#L51-L92),
[`LoadedModel`](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy/model_management.py#L771-L848),
[executor cleanup](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/execution.py#L839-L846).

## Partial unload, detach and patch identity

`load_models_gpu` deduplicates requested models, reuses managed wrappers, handles
clones, budgets by device and selects how much to load. The CPU branch bypasses
the device free-memory calls and disables VRAM policy
([managed load](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy/model_management.py#L939-L1038)).
`free_memory` chooses eligible wrappers and invokes `model_unload`; dynamic
models may instead rely on on-demand freeing when serving other dynamic models
([freeing policy](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy/model_management.py#L893-L937)).

`LoadedModel.model_unload(memory_to_free)` first tries a partial unload when the
target is smaller than loaded bytes. If that frees enough, it returns **False**:
the wrapper remains registered. True means the full detach path was taken.
Counting only removed wrappers therefore undercounts partial freeing
([return contract](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy/model_management.py#L835-L848)).

For the static patcher, a changed patch UUID or force-patch flag can require
unpatch/reload. Unpatch restores weight backups/object patches and clears
bookkeeping; its actual device movement depends on arguments
([static partial load](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy/model_patcher.py#L1276-L1302),
[unpatch](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy/model_patcher.py#L1150-L1189)).
Do not treat model shape/name equality as sufficient weight or patch identity.

## Dynamic backend boundary

`ModelPatcherDynamic` routes CPU construction to the static ModelPatcher and
keeps per-device pin state and a VBAR-backed loaded-size path. Its partial unload
calls the external VBAR allocator and may restore loaded backups; its
`partially_load` deliberately returns None rather than a static loaded-byte
delta
([construction and state](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy/model_patcher.py#L1771-L1840),
[dynamic unload](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy/model_patcher.py#L2064-L2097),
[dynamic load](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy/model_patcher.py#L2151-L2185)).
The external native allocator is not established by reading its Python caller.
Host registration/accounting, CUDA runtime operations and physical release need
the matching backend. CPU import/tests cannot establish those behaviors.

Sampler cleanup is also not synonymous with global model unloading. The normal
path cleans patcher/control/additional-model state and drops sampler references;
the executor separately unloads all models when smart memory is disabled, and
the OOM path has its own unloading action
([sampler cleanup](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/comfy/samplers.py#L1263-L1274),
[executor policy](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/execution.py#L839-L846),
[OOM path](https://github.com/Comfy-Org/ComfyUI/blob/b1a247c9cf9dbfda4b2c0a0c1d50950667eeaa0c/execution.py#L621-L647)).

## Troubleshooting and verification

| Symptom | Check before changing policy |
|---|---|
| A model “unload” frees less than expected | Distinguish partial/full path, live consumers, loaded-weight counters, allocator-reserved bytes, pinned-host registrations and synchronisation boundary |
| A new adapter causes a reload | Record patch UUID and clone identity; verify restored and repatched values rather than bypassing identity checks |
| More result caching increases memory pressure | Budget output tensors, model/pin residency and temporary sampler workspace together; a hit-rate improvement alone is not a service improvement |
| CPU test passes, accelerator run fails | Confirm actual patcher/backend path, effective flags, allocator dependency versions and model dtype; rerun the actual required path |

**HYPOTHESIS.** This ownership ledger can help another workflow engine decide
whether a memory policy trades transfers for recomputation. Transfer is valid
only after identifying equivalent owners/lifetimes and measuring the same
workload's output correctness, peak device/host/pinned bytes, reload counts and
end-to-end time. No ComfyUI speedup, memory reduction, GPU/NPU qualification or
LLM KV-cache equivalence has been measured for this candidate.
