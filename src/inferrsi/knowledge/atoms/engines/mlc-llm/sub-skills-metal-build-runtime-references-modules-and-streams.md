# Pinned TVM module, payload and storage/stream consumer

All paths below belong to [mlc-ai/relax at the MLC gitlink](https://github.com/mlc-ai/relax/tree/201fa0001c81431ccce05419b442c47779ea917c),
not an arbitrary current Apache TVM build. Source semantics do not authenticate
compiled artifacts, loaded devices or observations.

## Codegen and binary serialization are not execution

Selected [BuildMetal](https://github.com/mlc-ai/relax/blob/201fa0001c81431ccce05419b442c47779ea917c/src/backend/metal/codegen/codegen_metal.cc#L563-L648)
rewrites pointer value types, requires device-kernel calling convention and
global symbols, emits MSL per kernel and records function metadata. Buffers,
packed scalar arguments, address scopes/thread bindings and barrier semantics
are compilation contracts, not numerical evidence for arbitrary schedules.
Global barriers are explicitly unsupported; shared and SIMD barriers differ.

Without a compile callback, payload format is metal source. Legacy callback
str/bytes returns mean **compiled metallib**, even if those bytes happen to look
like MSL. An explicit (payload,format) may select metal or metallib; inconsistent
formats across kernels are rejected. Preserve format plus actual bytes/identity,
not a file extension or an assumption that any returned string is source.

The [factory](https://github.com/mlc-ai/relax/blob/201fa0001c81431ccce05419b442c47779ea917c/src/backend/metal/codegen/metal_fallback_module.h)
uses ffi.Module.create.metal when registered, otherwise creates a fallback;
TVM_COMPILE_FORCE_FALLBACK can also force it. The [fallback](https://github.com/mlc-ai/relax/blob/201fa0001c81431ccce05419b442c47779ea917c/src/backend/metal/codegen/metal_fallback_module.cc)
reports kind=metal and binary-serializable, but not runnable, and GetFunction
throws. Cross-compilation export can succeed without a linked Metal runtime.
Checking kind, inspecting source or saving bytes cannot prove kernel invocation.

Real and fallback serialize fmt, function metadata and per-kernel payloads,
**not** the in-memory inspection source map. The real loader reconstructs an
empty source map. Absent InspectSource after load does not by itself show lost
runnable code. Actual runtime factory/loader and native invocation remain needed.

The [real runtime module](https://github.com/mlc-ai/relax/blob/201fa0001c81431ccce05419b442c47779ea917c/src/backend/metal/runtime/metal_module.mm)
loads source or metallib and caches per-device/function pipelines under a mutex.
Source compilation uses fastMath and MSL 2.3 unless compiled SDK support plus
runtime OS/device Metal4 support permit MSL 4.0. Precompiled metallib has its own
artifact provenance. Invocation packs buffers/scalars, checks pipeline threadgroup
limits, obtains the selected thread/default stream encoder and dispatches
threadgroups. Pipeline creation is not dispatch; submission is not completion.

## Unified memory does not make every buffer shared or every copy blocking

The [DeviceAPI](https://github.com/mlc-ai/relax/blob/201fa0001c81431ccce05419b442c47779ea917c/src/backend/metal/runtime/metal_device_api.mm)
allocates main data buffers private; staging/readback buffers use shared storage.
CPU addressing, alias identity, byte offsets and stream ownership must follow
actual branches. Metal-to-Metal copies require the same device and append a
blit. CPU-to-private copies use pooled staging and queue blits without waiting.
The source pool's 64-buffer flush threshold is not tuning advice or a lifetime
proof for another stream.

In [Stream](https://github.com/mlc-ai/relax/blob/201fa0001c81431ccce05419b442c47779ea917c/src/backend/metal/runtime/metal_common.h),
compute/blit encoders share a pending command buffer. Flush ends/commits it;
**Flush does not wait**. Synchronize flushes and waits for a subsequent command
buffer on that stream. Private Metal-to-CPU readback stages shared memory and
waits before memcpy; the separate shared-source branch flushes then memcpy
without its own explicit wait. Do not infer a blanket blocking-copy guarantee
from the function's general comment.

FreeDataSpace checks the device default stream's HasPendingWork, literally
whether a pending command buffer exists, and synchronizes that branch before
purge/release. It is not a proof about every submitted/in-flight buffer or
external/custom stream. Completion handlers retain errors, dispatch can return
early after an error, and sync reports it. Last-kernel diagnostics/default-stream
counters are not request-indexed telemetry or GPU timing under concurrency.
These are source boundaries, not a confirmed runtime bug or global safety proof.
