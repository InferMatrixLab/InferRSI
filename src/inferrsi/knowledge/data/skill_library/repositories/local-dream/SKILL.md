---
name: local-dream
description: "Audit Local Dream Android desired-versus-serving process state, remote exposure, native backend and DiT packaging/ABI selection, shared generation cancellation and prompt-cache identity without mistaking declarations or source tests for on-device diffusion qualification."
license: NOASSERTION
disable-model-invocation: true
metadata:
  disco-role: operating
---

# Local Dream Android diffusion boundary audit

Use this source-derived **candidate** when a model page reports the wrong
backend, a quick reopen races a stop, host mode changes reachability, DiT fails
to load, generation appears stuck, or prompt-cache reuse is suspect. Start with
[source identity and rights](references/repo-provenance.md). This is original
bounded analysis of `xororz/local-dream`, not an Android installer, device
compatibility certification or a managed DisCo import.

## Route to the failing boundary

| Symptom / question | Procedure |
| --- | --- |
| Same model but wrong resolution/backend/bind address; stop/reopen/restart; stale Error | [Android desired/serving lifecycle](references/android-lifecycle.md) |
| Remote control says Ready, or comments imply pairing/authentication | [Actual host exposure and readiness](references/android-lifecycle.md); never enable host mode as a diagnostic default |
| CPU/MNN versus QNN versus Anima versus dynamically loaded DiT; SSE disconnect or upscaler contention | [Native dispatch, cancellation and cache](references/native-contracts.md) |
| Missing engine/entry point/ABI/skel, QNN runtime mixing, APK versus DSP packaging | [Packaging and native prerequisites](references/packaging-and-abi.md) |
| Same prompt gives suspicious reuse after export/model/textual-inversion changes | [Cache identity and caller guards](references/native-contracts.md); shape/header acceptance is not model-revision invalidation |
| Only declarations are available | [Offline declaration screen](scripts/screen_declarations.py), whose explicit non-native limits are below |

## Establish identities before suggesting a change

1. Record the source revision, installed APK/version/flavor/ABI, actual native
   executable and separately loaded DiT library, QNN/Hexagon/MNN build identities,
   selected model/export/weight/tokenizer identities, requested configuration and
   **serving** configuration. Use anonymized IDs and `<MODEL_PATH>` in shared
   reports. A source version string or file existence is not installed identity.
2. Follow actual backend dispatch, not the README headline. SD1.5/SDXL MNN and
   QNN paths, Anima and `zimage`/`klein`/`qwen21`/`krea2turbo` DiT routing are not
   interchangeable. A UI `runOnCpu` flag does not alone specify the executed
   MNN CPU/GPU provider or the DiT engine's device/parameter residency.
3. Compare the full process configuration: model, backend type, width, height
   and `listenOnAll`. A process still alive in the stop grace window is not
   evidence that it serves the newly requested configuration. Follow both
   process state and health/config observations. `Running` is published after
   process start, before proven native readiness; the local health consumer
   checks model identity but not every serving field. Ready is not image
   completion. Equality also omits startup preferences and changed model bytes;
   an equal tuple is not proof that such changes were applied.
4. Separate startup, model load, prompt encoding, denoising, VAE work, preview,
   safety filtering, final response, history persistence and teardown. SSE
   progress, a client cancellation request, native completion, buffer release
   and saved final output are different events. Native/shared resource locks
   can serialize generation and upscaling; do not infer parallel NPU capacity.
5. Treat persistent prompt caches as model-directory-scoped implementation
   caches, not authenticated model-revision namespaces. Check mode, version,
   dimensions and callers' textual-inversion bypass. Preserve failure signals
   rather than deleting caches or model directories without authorization.

## Safe offline use

The bundled standard-library helper reads a small explicit declaration object
from stdin or one regular JSON file; it makes no network, subprocess, Android,
model, tensor, native-library, filesystem-discovery or device calls. It compares
the five declared configuration fields and separately declared ABI/SDK labels.
It does **not** reproduce coroutine timing, resolution snapping, Android service
rules, dynamic loading, symbol-table validation, runtime stamping/copy behavior,
prompt-cache formats or native execution.

```bash
python <skill-dir>/scripts/screen_declarations.py --example
python <skill-dir>/scripts/screen_declarations.py <anonymized-declarations.json>
```

An equal configuration can still be dead, unready or serving stale bytes. Equal
ABI/SDK labels can still describe incompatible or corrupted artifacts. The
helper returns field names and fixed diagnostics, not supplied identifiers; it
always retains `native_execution: not_run` and `qualification: INCONCLUSIVE`.
Its zero exit means valid input and completed screening, not native success.

## Evidence required for a stronger conclusion

Required Android/ARM64 and actual selected MNN/QNN/Hexagon/model execution remains
`BLOCKED_REQUIRED_BACKEND / not_run`; there is no full CPU substitute for it.
Source assertions, Gradle configuration, offline helper tests and InferRSI wheel
access are separate evidence classes. No upstream test, APK build/sign/install,
native loader, live HTTP endpoint, model/image quality, memory fit, thermal,
latency, throughput, service or broad skill-efficacy result is claimed here.

For an authorized future run, freeze a RunSpec and workload first. Require
actual backend identity, model/tokenizer/export hashes, load and readiness
records, final image plus quality validator, cancellation and teardown outcomes,
memory/thermal controls and complete timing boundaries appropriate to the claim.
Source hardware gates and implementation constants are not portable acceptance
thresholds. Return the failed boundary, counter-signal, identities observed vs
declared, smallest missing discriminator and retained `INCONCLUSIVE` scope.

Upstream's pinned LICENSE is **CC BY-NC 4.0**, while repository API SPDX metadata
reports `NOASSERTION`. The latter is preserved, not permission for commercial
reuse or relicensing. See [rights and exclusions](references/repo-provenance.md).
