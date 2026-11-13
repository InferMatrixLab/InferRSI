# Stack selection and installation

## Choose one version contract

The source snapshot is a development branch, not an installed release. Its
`version.txt` lists package build lines 2.13.0, 2.14.0, 2.15.0 and 2.16.0. The
release compatibility document at the same pin includes a recommended
2.12.0 package/PyTorch pair with CANN 9.1.0 and also rows for product 26.2.0
with CANN 9.2.0. These are different contexts, not a guarantee that every listed
component can be mixed. Package `.postN` is not a CANN or product-version suffix.
Retain the selected release row, Python ABI and hardware-specific driver/firmware
requirements together. Do not install development master against a released
2.12 wheel and call the result source-aligned. Evidence: F1, F2 in the
[source map](../../../references/source-map.md).

Create a private environment for the selected release. Substitute versions
from a single approved row:

```bash
source <CANN_ROOT>/set_env.sh
python -m pip install 'torch==<TORCH_PACKAGE_VERSION>' --index-url https://download.pytorch.org/whl/cpu
python -m pip install 'torch-npu==<TORCH_NPU_PACKAGE_VERSION>'
python -m pip check
python <SKILL_ROOT>/scripts/inspect_environment.py
python <SKILL_ROOT>/scripts/inspect_environment.py --device
```

The CPU PyTorch wheel is the framework foundation for the NPU plugin; it does
not turn NPU execution into CPU verification. Explicit `import torch_npu` is
useful even with automatic backend loading because it exposes plugin import
failure directly. The probe prints package versions and public readiness
signals, without filesystem locations, environment dumps or device serials.

## Source build contract

Use an isolated, disposable Linux checkout when intentionally developing the
adapter. Preserve its exact revision and all gitlink revisions. Install the
matching torch build first. `tools/setup_helpers/version.py` uses `TORCH_VERSION`
when present, otherwise installed `torch.__version__` with the local build tag
removed; `setup.py` uses that result for the torch release-prefix dependency.
`version.txt` documents build lines; it does not by itself determine setup's
version. Build flags, target ABI and the installed torch headers must agree.

The source build integrates `torchnpugen`, op-plugin-generated registrations,
libtorch_npu, optional TorchAir, FXRT and RPC. Treat `DISABLE_INSTALL_TORCHAIR`,
`DISABLE_INSTALL_FXRT` and `DISABLE_RPC_FRAMEWORK` as build-time scope choices,
not runtime cures for arbitrary import failures. Record the resulting wheel's
features. The inspected setup invokes submodule initialization and code
generation during metadata/build execution, and `generate_code.sh` copies ACL
headers then recursively removes its `third_party/acl_src` working directories.
Consequently do not execute setup for a read-only version query or reuse its
build scripts as generic skill helpers. Prepare full submodules/toolchain first
and use a disposable build workspace. This operating skill intentionally does
not bundle that mutating pipeline.

## Acceptance

An import observation, positive device count, successful tiny allocation,
synchronized matrix multiply and correct host result are separate checks.
Record which occurred. A compiler route also needs the chosen compiler package;
HCCL requires an actual multi-rank check. Use the [graph route](../../graph-and-compile/SKILL.md)
or [distributed route](../../distributed-and-hccl/SKILL.md) for those gates.
