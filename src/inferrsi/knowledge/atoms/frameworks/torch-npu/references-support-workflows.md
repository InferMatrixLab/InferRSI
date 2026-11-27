# Support workflows and capability boundaries

Use these routes to keep less common tasks discoverable. “Inventoried” means
the directory/API surface was found; it does not claim implementation depth,
runtime support or a complete recipe. The source manifest records actual reads.

| Surface | Route and concrete procedure | Evidence boundary / required check |
|---|---|---|
| Broad migration shim | Select `torch_npu.contrib.transfer_to_npu` explicitly in a fresh process; inventory converted device strings and patched APIs; compare one fixed eager model before adding compile/distributed execution. | Inspected whitelist/device-proxy boundary; process-wide monkeypatching cannot port custom CUDA binaries or qualify every dependency. |
| Checkpoint/serialization | Use explicit state-dict save/load placement; verify model, optimizer, scaler and RNG round trip and a resumed step. Hold tensors until any selected async save has completed. | Serialization imports/remapping inspected; async writer and legacy/custom storage paths not fully traced. Never load an untrusted arbitrary pickle as a smoke check. |
| ONNX export | Import the intended TorchNPU ONNX registration only when exporting; retain opset, shape/dtype and custom operator identities; validate exported outputs on the target consumer. | Import calls wrapper registration; per-operator symbolic/export-runtime coverage inventoried only. Exported graph creation does not prove runtime kernel availability. |
| JIT/LibTorch deployment | Freeze input/output schema and selected trace/script mode, retain device ops and ABI; compare Python and deployed C++ outputs on fixed inputs. | Example/build roots inventoried; model/download/toolchain-dependent examples remain reference-only. The graph route covers the deployability boundary, not a prebuilt binary. |
| Fused optimizers/modules | Change one optimizer/module at a time; keep parameter groups, hyperparameters, state dtype and numerical comparison. | Optimizer exports inspected; every optimizer algorithm and contrib quantized/attention/detection module is not traced. Names do not establish numerical equivalence. |
| HiFloat8/quantized formats | Preserve tensor scale/layout/dtype, conversion boundaries and actual hardware/operator support. Validate round-trip and end-to-end accuracy before performance claims. | `custom_dtype`, `hif8_tensor`, contrib quantized modules and op-plugin quant schema are inventoried; full format math/kernels are outside the selected readset. |
| DTensor/FSDP | Record global/local shapes, placements, device mesh and process groups; first check local operator semantics and HCCL, then one sharded step. | DTensor rule-module registration inspected; placement strategy formulas and FSDP patch internals inventoried only. No blanket sharding support claim. |
| Distributed functional/pipeline | Specify autograd participation, stage ordering and group identities; verify matching send/receive shapes and every rank's completion. | Owning directories inventoried; full pipeline scheduling and functional-gradient semantics unverified. |
| RPC/Tensorpipe | Qualify explicit transport, worker mapping and process lifetime; compare a tiny authorized request/response on an isolated allocation. | Parent transport code present; Tensorpipe gitlink not fetched. HCCL collective results cannot validate RPC. |
| Symmetric memory/SHMEM | Establish external runtime, participating ranks and symmetric allocation/visibility contract before any operation. | Public wrappers/C++ directory inventoried; external SHMEM and device memory visibility unverified. Do not substitute ordinary allocator memory. |
| Fault detection/UCE/recovery | Preserve first fault, exact mode and bounded reproducer; escalate device reset/restart/stress only under the caller's explicit operational scope. | `asd`, checksum, recovery and stress surfaces inventoried, sanitizer entry inspected. Neither health certification nor a safe automatic recovery recipe is claimed. |
| DLPack/multiprocessing/IPC | Record exporting allocation owner, device, stream, capsule/process lifetime and consumer completion; retain the original owner until handoff contract is satisfied. | Wrappers/IPC directories inventoried; not all capsule, shared-memory or interprocess transport paths traced. Stream route covers general ownership obligations only. |
| Maintainer generation/build/CI | Use a disposable source checkout, exact dependencies/gitlinks and the owning build policy; review generated registrations rather than editing them by hand. | Setup/codegen source read; CI scripts may install, download, mutate environments or publish results and are not reusable runtime smoke commands. |

When a task reaches an inventoried-only boundary, return the known entry point,
required input/ownership contract and the missing implementation/runtime evidence.
Do not fabricate a complete specialized procedure from a directory name. The
root's eight primary routes remain usable without reopening source documentation;
new expert work beyond their evidence requires a scoped follow-up readset.
