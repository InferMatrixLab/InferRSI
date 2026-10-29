# Separate APK, CPU loader and DSP artifacts

All source links below name Local Dream
`db162df4d9bb6efc6595250423d8df26241f4c27`; source declarations are not observed
build or device results. This procedure is original analysis, not copied build
code and not authorization to run the referenced scripts.

## Reconstruct the build boundary

1. Identify the actual app flavor and native package. The
   [Gradle manifest](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/build.gradle.kts#L28-L107)
   declares version `3.0.0-alpha.6`, min SDK 28, compile SDK 37, target SDK 36,
   ARM64-only filtering, legacy JNI packaging and `basic`/`filter` flavors.
   Source declarations do not prove the installed APK used those settings.
   Both debug and release refer to the release signing configuration; do not
   solicit or inspect signing secrets as a smoke-test prerequisite.
2. The core's
   [CMake owner](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/CMakeLists.txt#L1-L41)
   copies a QNN SampleApp from an externally provided SDK and applies a local
   patch during configuration. It stages QNN HTP/System libraries plus
   architecture-specific stubs/skels and SDK notices. The root
   [build script](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/build.sh#L1-L16)
   stages the **executable** named `libstable_diffusion_core.so` into JNI
   packaging; its `.so` spelling does not make it the DiT shared library.
3. The separate
   [DiT build](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/dit/CMakeLists.txt#L1-L81)
   links the pinned stable-diffusion.cpp fork, forces the ggml Hexagon backend,
   applies local patches to that fork and ggml, and exports one ABI entry point.
   Core and engine are separate projects specifically to avoid imposing the
   engine's newer instruction set/API requirements on every core path.
4. Distinguish host and DSP binaries. The
   [DiT staging script](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/dit/build.sh#L22-L59)
   builds an ARM64 CPU-side `libdit_engine.so` at Android API 28 with its own
   architecture flags. It puts that library in JNI packaging, but puts
   `libggml-htp-v79/v81/v85.so` **DSP** skels in assets. FastRPC, not the Android
   CPU loader, loads the latter after runtime copying. Putting all `.so` files
   into the same Android ABI directory is not a valid packaging repair.
5. Record gitlink plus patch plus SDK identity, not just repository HEAD.
   [`.gitmodules`](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/.gitmodules)
   points stable-diffusion.cpp at `happyyzy/stable-diffusion.cpp`; the gitlink is
   `a63954dc794f6daade32c407da1a9c4bc2d73cf0`. MNN's gitlink is
   `413b1c3c53d0d579e30848983b244aa82b2fbeee`. These dependency bodies and
   nested ggml are **not inspected** in this skill. Local patch presence is
   known from build ownership, not an audited patch-semantic or build result.

## Diagnose loader failures in order

| Observation | Discriminator | Do not conclude |
| --- | --- | --- |
| Engine file missing | Installed APK/native-library directory and model selection; [existence check](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/data/DitEngine.kt#L15-L34) only checks a path | Existence proves compatibility, authenticity or loadability |
| `dlopen` fails | Actual binary architecture, CPU feature/API requirements, dependency resolution and loader error | All Snapdragon devices support the DiT binary |
| Entry point absent | Actual exported symbol and version-script/build identity | Matching filename proves the C ABI |
| ABI mismatch | Caller and returned API version; [header](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/include/DitEngine.h#L13-L36) requests version 5 at this pin | A declared matching integer verifies struct layouts or function pointers |
| Engine create fails | Error from `last_error(nullptr)`, exact model components/backend/parameter placement | QNN bring-up and ggml Hexagon creation are interchangeable |
| HTP runtime/skel failure | CPU library vs DSP skel identity, selected HTP family, SDK and staged bytes | App min SDK or README SD1.5 support establishes DiT support |

These stages are explicit in
[PipelineDit initialization](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/PipelineDit.hpp#L49-L91).
The [Android DiT predicate](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/data/DitEngine.kt#L18-L28)
checks Android S+, an `SM` part-number prefix and numeric value at least 8750;
its source comment's validation claim is upstream-reported, not reproduced here.
It admits future numeric part numbers without probing every runtime capability.
README SD1.5 V68+ and SDXL 8 Gen 3+ claims must not overwrite this different gate.

## Track native ownership, not one broad "load succeeded"

QNN's [runtime initializer](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/src/QnnRuntime.hpp#L20-L132)
resolves system function pointers, creates model handles and then performs
backend/device/profiling/op-package/context bring-up. A successful early dynamic
lookup does not establish every later stage. Its selected lazy-loading wrapper
hands the model library handle to `QnnModel` for destruction; no repeated-cycle
leak test is run here and the destructor's full implementation is not audited.

For DiT, the [C API](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/cpp/include/DitEngine.h#L91-L132)
separates create/destroy, generate, owned output pixels and `free_image`.
Progress with zero total can represent auxiliary work rather than denoising.
`cfg_scale` and distilled guidance are distinct API values. The wrapper forces
direct VAE convolution for the selected repacked Hexagon layout; do not remove
it as a cosmetic performance toggle based on a successful CPU run. This is
source rationale, not independent validation of the underlying ggml kernels.

## Authorized future verification sequence

First inspect anonymized artifact manifests and hashes offline. Only with
separate native execution authority prepare version-matched Android SDK/NDK,
QNN and (for DiT) Hexagon SDK, initialized pinned dependencies plus exact patches,
and an actual supported device/model. Record build, package contents, CPU loader,
DSP discovery, create, generate, image validation and teardown separately. Never
publish SDK binaries, keys, weights or device identifiers here. SDK notices and
redistribution rights are separate from Local Dream's CC BY-NC 4.0 LICENSE.

Native preparation and every stage above remain `BLOCKED_REQUIRED_BACKEND /
not_run`. CMake flags, source version 5, script comments and matched declarations
are not a passing native build or an empirical model/quality/fit/service result.
