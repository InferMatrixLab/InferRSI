# Installation troubleshooting

| Symptom | Source mechanism | Recovery and discriminating check |
|---|---|---|
| `libascendcl.so` missing | Core loader requires CANN runtime library | Confirm runtime installation and source its process-level environment script; retry import in a fresh interpreter. |
| `libhccl.so` missing | C extension/distributed loading needs communication/compiler libraries | Check the matching CANN package layout and environment; reinstalling Python alone does not supply HCCL. |
| `ASCEND_OPP_PATH` missing or nonexistent | Registry checks toolkit/ops paths when `ASCEND_HOME_PATH` exists | Install the proper ops package and re-source the selected CANN environment; avoid combining paths from two toolkits. |
| Two accelerators conflict | Import checks active accelerator; unsupported non-CPU/non-NPU accelerator raises | Select a compatible CPU torch foundation for the NPU environment. `TORCH_DEVICE_BACKEND_AUTOLOAD=0` is for intentionally suppressing automatic backend load, not proving simultaneous accelerator support. |
| `torch.npu` exists but allocation fails | Registration and lazy device initialization are different phases | Run the opt-in device probe and retain original initialization error. Verify driver/device exposure and exact CANN stack. |
| Source wheel gets an unexpected version | Setup derives version from `TORCH_VERSION` or installed torch | Inspect intended target and installed headers; rebuild a consistent pair in isolation. |
| CPU import works on another host | It does not exercise NPU allocator or runtime | Keep device checks blocked, with the exact required backend named. |

Do not suppress import exceptions or change shared library search paths blindly.
Preserve the first failing phase and relevant sanitized message. Re-run import
from outside a source checkout to avoid masking missing installed files.
