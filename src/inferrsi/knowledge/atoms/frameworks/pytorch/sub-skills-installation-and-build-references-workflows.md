# Installation, builds and package identity

## Inputs and outputs

Inputs: OS/architecture, Python ABI, intended CPU/CUDA/ROCm/XPU/MPS backend,
binary versus source requirement, supported device/driver/toolkit and dependency
constraints. Output: a reproducible install/build plan, actual distribution and
build identity, import/device smoke and explicit unavailable prerequisites.

## Binary workflow

1. Select a documented wheel for the exact platform and Python ABI. Keep its
   source/index, version and backend tag together; a CUDA-capable system can
   still import a CPU wheel. `torch.version.cuda`/`hip` describe the build,
   while `torch.cuda.is_available()` describes runtime availability.
2. Create a private virtual environment with supported Python. The pinned
   source requires Python >=3.11; a historical wheel may differ. Avoid installing
   into the interpreter running an unrelated application.
3. For CPU inspection a concrete command pattern is
   `python -m pip install torch --index-url https://download.pytorch.org/whl/cpu`.
   Resolve and record the actual version; this command is deliberately not a
   pin to the source revision. Use the official backend selector for another
   wheel and verify that wheel's supported architecture/driver independently.
4. Run `python -m pip check`, then the bundled root environment inspector from
   outside any directory named `torch`. Optionally add `--require-backend cpu`
   or the actual device type. The inspector never allocates a device tensor.
5. A minimal real-device preparation smoke is `torch.ones(1, device=device)+1`,
   followed by that backend's synchronize operation before reading results.
   Record the device actually used. CPU import is no substitute for this check.

No GPU toolkit is required for ordinary CPU-wheel use. Building CUDA extensions
does require a toolkit/compiler independently of the runtime libraries bundled
with many wheels. A successful pip resolver does not prove ABI or kernel support.

## Source build workflow at this snapshot

The authoritative build backend is **scikit-build-core**, declared in
`pyproject.toml`. The small `setup.py` only forwards historical install/develop
commands or rejects unsupported commands. Do not use an older setup.py recipe.

1. Obtain a trusted, explicitly selected source revision and initialize its
   recursive submodules for an actual build. A shallow no-submodule source
   inspection checkout is sufficient for reading and insufficient for compiling.
2. Prepare Python >=3.11, a C++20 compiler, CMake/Ninja and enough memory/disk.
   Windows needs Visual Studio Build Tools, not just a code editor. CUDA needs
   a compatible toolkit, host compiler and cuDNN; ROCm build support here is
   Linux-specific. XPU needs the matching Intel stack; MPS needs macOS.
3. Install the pinned source's declared build requirements before requesting
   `--no-build-isolation`. The metadata includes NumPy, packaging>=24.2,
   pyyaml, scikit-build-core>=1.1.1, typing-extensions>=4.15.0 and six.
   The documented developer path uses `pip install --group dev`; it is broader
   than runtime-wheel inspection and should be selected only for development.
4. Use the repository's current build entry:

   ```bash
   python -m pip install --no-build-isolation -v -e .
   ```

   Here `.` is the explicitly selected source project when performing a source
   build. Runtime diagnostic helpers below require only an installed package.
5. Select build variables before configuration: `USE_CUDA=0`, `USE_ROCM=0`,
   `USE_XPU=0`, `BUILD_TEST=0`, `MAX_JOBS`, `DEBUG` or `REL_WITH_DEB_INFO` as
   appropriate. Keep the exact settings with the build log; do not enable every
   backend. MAX_JOBS maps to CMAKE_BUILD_PARALLEL_LEVEL unless that is set.
6. `cmake/EnvVarForwarding.cmake` forwards BUILD_/USE_/CMAKE_ prefixes and its
   explicit aliases/passthrough list. Arbitrary environment names do not become
   CMake options. For nonforwarded options use pip config settings, e.g.
   `-Ccmake.define.DEBUG_CUDA=ON` only when that option is intended and supported.
   CMAKE_ONLY/CMAKE_FRESH/USE_NINJA are removed legacy controls.
7. On Windows this pyproject selects Ninja and defaults host CC/CXX to `cl`
   unless explicitly set. The README retains older generator guidance: prefer
   the active pyproject implementation when these conflict. Do not silently
   change global PATH or a system compiler to repair one project.
8. Verify the installed package outside the source tree. Record the build's
   actual git identity and configuration, then execute tiny CPU and required
   device checks. A successful build with CUDA disabled does not qualify CUDA.

## LibTorch and extension consumers

Keep C++ headers, libraries, runtime library paths, build type, compiler and ABI
from the same compatible distribution. `torch.utils.cpp_extension` is the
Python extension entry, covered by the custom-operator route. Do not mix a
system LibTorch with headers or extensions from another Python wheel. Source
codegen (`torchgen`/ATen YAML) and CMake files are build inputs, not user imports.

## Acceptance and refresh

Preserve the wheel version and `torch.version.git_version` independently of
source provenance. An API signature existing in an installed release does not
prove that the entire pinned main source runs on that release. Reinspect changed
build metadata, dependency floors and backend prerequisites after revision drift.


Source support at the pinned revision (exact inspected spans and byte digests are in the root [readset](../../../references/source-readset.json)):

- [`README.md`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/README.md)
- [`pyproject.toml`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/pyproject.toml)
- [`setup.py`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/setup.py)
- [`cmake/EnvVarForwarding.cmake`](https://github.com/pytorch/pytorch/blob/9a90a4fefcaafa63ac984621963a6fcc66aee68c/cmake/EnvVarForwarding.cmake)
