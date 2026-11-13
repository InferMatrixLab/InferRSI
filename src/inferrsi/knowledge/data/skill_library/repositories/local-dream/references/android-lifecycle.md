# Android desired state, readiness and remote-host boundaries

This is original procedural analysis of **xororz/local-dream** at
`db162df4d9bb6efc6595250423d8df26241f4c27`, not copied implementation or an
Android test result. Upstream source is CC BY-NC 4.0; retain its attribution and
noncommercial restriction when reusing source material. This reference makes no
commercial-use, redistribution or dependency/model-license compatibility claim.
Native execution is `not_run / BLOCKED_REQUIRED_BACKEND`; qualification remains
`INCONCLUSIVE`.

## 1. Identify the process, not merely the selected model

Record a redacted declaration of the desired model ID, backend type, width,
height, local/host mode, process identity and relevant APK/runtime/model artifact
identities. Distinguish four observations: a start command was accepted, a
process was created, the service reports a serving configuration, and the native
health endpoint responds. None alone proves successful generation or quality.

The [model mapping](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/data/Model.kt#L117-L163)
selects DiT kind first, then Anima, then SDXL (`sdxlmnn` when `runOnCpu`), then
SD1.5 CPU or NPU. The explicit DiT kinds recognized by
[BackendService](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/service/BackendService.kt#L87-L94)
are `zimage`, `klein`, `qwen21` and `krea2turbo`; upscaler mode is a separate
pseudo-backend. Do not reduce this pin to the README's SD1.5/SDXL headline or
infer a native implementation from the `runOnCpu` field name alone.

The service's [configuration equality and command parser](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/service/BackendService.kt#L157-L249)
cover **model ID + backend type + width + height + listenOnAll**. A process with
the right model but the wrong bind scope or dimensions is not the same desired
configuration. `listenOnAll` is the OR of the explicit persisted LAN preference
and current `RemoteHostService.isRunning`; host mode itself is not inferred from
a stale saved host-mode flag. Therefore leaving host mode does not prove the
separate LAN preference is disabled.

Not every startup input is part of this equality tuple. The
[startup command builder](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/service/BackendService.kt#L494-L596)
reads img2img, low-RAM and Anima sequential-DiT preferences and checks `V_PRED`
and patch files. **Diagnostic inference:** equality-based reuse alone does not
prove those inputs were re-read after a preference or file change. Capture actual
startup inputs and a new process observation if their change matters; do not
claim automatic model-byte or preference invalidation from config equality.

## 2. Reconstruct the desired → serving transition

The [single control dispatcher and state](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/service/BackendService.kt#L27-L75)
serialize process-management work. Reconstruct the ordered commands rather than
assuming that screen navigation synchronously stops a process:

1. A valid start cancels pending idle teardown, writes `desired`, then reconciles.
   A null parsed configuration reports an error and returns before that update.
2. Reconciliation waits for `runtimeDirReady`; preparation failure is not fixed by
   repeatedly treating the service as ready. If the tracked process is alive and
   its full `serving` tuple equals `desired`, reuse occurs unless force-restart
   was requested.
3. Otherwise the old backend is stopped, the model-storage move guard is checked,
   and startup is attempted. `serving` is published after `startBackend` returns
   true. That function returns after `ProcessBuilder.start()` and monitor setup,
   **not after native model loading or an HTTP health check**.
4. Stop writes `desired = null`, then schedules the source's 1500 ms grace. A new
   valid start cancels the pending stop. At expiry a still-empty desired state
   stops the process; `stopSelfResult(startId)` guards service shutdown against a
   newer start. In host mode the foreground service is retained for later remote
   selections, even when there is no running backend.

These are [source transitions](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/service/BackendService.kt#L239-L313),
not a proof that all Android lifecycle interleavings are race-free. The 1500 ms
value is an implementation detail at this pin, not a portable latency gate.

For an apparent crash during model switching, check whether the monitor belongs
to the current tracked process and whether intentional stopping was active. The
[monitor and teardown](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/service/BackendService.kt#L657-L754)
only publish a live crash when `!stopping && process === proc`; teardown marks
intentional stop before destroying the process and clears serving identity.
Do not attribute a stale process exit to the new model. Conversely, suppression
of an expected exit is not evidence that the replacement loaded successfully.

## 3. Separate process state from local and remote readiness

The [screen always declares the local target](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/ui/screens/ModelRunScreen.kt#L1467-L1496)
rather than skipping start because a shared state happens to say Running.
Remote initial selection is sent before triggering readiness polling.

| Observation | Actual source check | What it does not prove |
| --- | --- | --- |
| Local readiness | Successful generation-port `/health` plus matching `servingModelId`; relevant error must persist for two polls | Matching width/height, backend type, model bytes, generation success or quality |
| Remote readiness | `/status` reports matching model ID, `running`, width and height, then generation-port `/health` succeeds | Atomic snapshot across endpoints, current tensor dimensions, authenticated host, model bytes or generation correctness |
| `/select` success | `startService` accepted the intent, and latest selected ID was recorded | Backend loaded or reached health readiness |
| `/stop` success | Control handler returned success, or ignored a superseded model ID | Process teardown has completed, generation rolled back, or network exposure has ended |

The [local and remote polling bodies](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/ui/screens/ModelRunSupport.kt#L92-L218)
are deliberately different. Local polling does **not** compare serving
resolution; remote polling does. The source's polling delays/timeouts are not
new benchmark acceptance thresholds. The two remote observations are sequential
HTTP exchanges, not an atomic transaction with generation.

A nondefault SD1.5 NPU request needs its actual patch. If the patch file is
missing, the [builder logs fallback without adding the patch argument](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/service/BackendService.kt#L547-L568)
while the service can still publish the requested configuration. Therefore a
matching reported resolution is not proof of effective native tensor shape.
The [remote screen narrows saved patch resolutions to the host catalog](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/ui/screens/ModelRunScreen.kt#L1443-L1455),
but a stale catalog or direct client still requires checking the actual asset.

DiT resolution paths also differ: local parsing snaps/clamps through
[DitResolution](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/data/DitResolution.kt#L5-L22),
whereas remote selection rejects unsupported DiT dimensions before sending the
intent. Record requested, normalized, reported and actually executed dimensions
separately; source UI limits do not establish memory fit at their upper bound.

## 4. Treat remote host mode as exposure, not pairing

**There is no authentication gate in the inspected control server.** Its
[implementation and explicit trust-model comment](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/remote/RemoteHostServer.kt#L14-L25)
describe unauthenticated LAN control, and
[route dispatch](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/remote/RemoteHostServer.kt#L161-L180)
contains no credential check. Older comments in
[RemoteProtocol](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/remote/RemoteProtocol.kt#L6-L40)
and `RemoteHostService` describe an authenticated API; do not elevate those
comments above the actual server. `/info` identity matching is discovery, not
cryptographic identity or pairing. No pairing guarantee is established here.

The control socket and native generation socket are distinct. The
[client](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/remote/RemoteApiClient.kt#L13-L108)
uses HTTP JSON for control and contacts the native generation port directly;
generation is not tunneled through a protected control channel. Do not enable
host/LAN mode, open firewall rules or expose services merely to run this audit.
Any later live test requires explicit authorization and an appropriately
controlled network. Never publish host addresses, prompts or catalog paths.

[Host startup](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/service/RemoteHostService.kt#L64-L123)
starts the control server, marks host state active and sends BackendService a
foreground standby command. The intent is to prepare for Android background
service restrictions before remote selection. Standby changes no backend model.
On host exit, the service first clears host state, then requests backend stop;
that request still follows the backend grace path and can fail to dispatch.
A disappearing host-mode UI alone is not a verified socket-closure observation.

[Select/status/stop handlers](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/service/RemoteHostService.kt#L165-L278)
track the most recent selected **model ID**, not a unique request generation.
A stop for a different model ID is ignored; an ID-less stop is unconditional.
A delayed stop for the same ID after reselection is not distinguished by that
guard. The [single control worker](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/remote/RemoteHostServer.kt#L206-L215)
orders handler work, but it does not make asynchronous backend startup complete
before the next request or provide per-controller ownership.

## 5. Distinguish interrupting generation from stopping the backend

The [screen interruption path](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/ui/screens/ModelRunScreen.kt#L1343-L1361)
cancels the batch job and stops BackgroundGenerationService while keeping the
backend available. [Generation stop](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/service/BackgroundGenerationService.kt#L116-L129)
sets cancellation intent, cancels the active HTTP call and reports Idle. The
[native request is a streaming HTTP call](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/service/BackgroundGenerationService.kt#L324-L354);
client socket closure is not instantaneous native cancellation, buffer release
or transactional rollback. Inspect native progress/disconnect handling separately.

The [exception path](https://github.com/xororz/local-dream/blob/db162df4d9bb6efc6595250423d8df26241f4c27/app/src/main/java/io/github/xororz/localdream/service/BackgroundGenerationService.kt#L553-L574)
preserves an already completed result across a teardown exception, maps requested
cancellation to Idle, and otherwise reports an error. A UI Idle observation
cannot distinguish every native phase. Verify authorized cancellation/retry
experiments with native completion/resource observations, not UI state alone.

## Diagnostic decision table

| Symptom | First discriminating inspection | Avoid concluding |
| --- | --- | --- |
| Reopening briefly retains the old process | Ordered desired/serving commands, grace pending/cancelled, full tuple equality | Leak solely from temporary process survival |
| Running but generation not ready | Process-spawn receipt versus native health, model identity and actual assets | Running means model loaded |
| Correct ID but wrong dimensions | Requested/reported dimensions, patch existence and native effective shape | Status fields authenticate tensor shape |
| Same model ignores changed startup preference | Equality tuple versus actual startup-only flags, process identity | Reuse re-evaluates every setting |
| New model receives old crash error | Monitor process identity, intentional-stop state, error model ID | Every exit belongs to the current model |
| Remote stop affects a later run | Target ID, latest selected ID, same-ID reselection and legacy ID-less stop | Model-ID guard is request ownership |
| Host mode ended but backend still reachable | Backend grace completion, dispatch failure, persisted LAN preference, authorized socket observation | Control server shutdown closes every socket immediately |
| Interrupt reports Idle but device remains busy | Active call cancellation versus native progress/disconnect phase | Cancellation is rollback or proven memory release |

Return the failed boundary, source revision, redacted requested/reported/observed
facts, applicable negative signal and smallest missing native observation. Do
not invent quality or performance gates from lifecycle constants.

## Exact inspected readset and verification limits

Paths below are relative to the pinned repository. Whole-file hashing by the
source ledger, if present, is identity evidence; it does not expand these
inspected spans.

| Source path | Inspected lines / purpose |
| --- | --- |
| `app/src/main/java/io/github/xororz/localdream/service/BackendService.kt` | 1–596, 625–755; state, command/config, grace/reconcile, runtime copy, startup flags, process monitor/teardown |
| `app/src/main/java/io/github/xororz/localdream/service/RemoteHostService.kt` | 1–395; host lifecycle, catalog/select/status/stop, source comments versus actual implementation |
| `app/src/main/java/io/github/xororz/localdream/remote/RemoteHostServer.kt` | 1–217; socket, parser/routes, absence of auth gate, single worker |
| `app/src/main/java/io/github/xororz/localdream/remote/RemoteProtocol.kt` | 1–150; protocol declarations, source-comment discrepancy, catalog fields |
| `app/src/main/java/io/github/xororz/localdream/remote/RemoteApiClient.kt` | 1–114; separate control/generation HTTP paths |
| `app/src/main/java/io/github/xororz/localdream/data/Model.kt` | 117–178; backend priority, canvas and package flags |
| `app/src/main/java/io/github/xororz/localdream/data/DitResolution.kt` | 1–23; snapping versus support predicate |
| `app/src/main/java/io/github/xororz/localdream/ui/screens/ModelRunSupport.kt` | 50–230; local/remote readiness and bounded adjacent context |
| `app/src/main/java/io/github/xororz/localdream/ui/screens/ModelRunScreen.kt` | 1310–1505, 1750–1810, 1838–1925; interruption, saved dimensions, start/restart and readiness call sites |
| `app/src/main/java/io/github/xororz/localdream/service/BackgroundGenerationService.kt` | 27–48, 108–148, 214–242, 320–355, 540–580, 645–673; cancellation/request/error/teardown only |
| `app/src/test/java/io/github/xororz/localdream/ExampleUnitTest.kt` | 1–17; trivial arithmetic test, not lifecycle coverage |
| `app/src/test/java/io/github/xororz/localdream/ModelStorageTest.kt` | 1–90; selected move/journal tests, not backend lifecycle execution |

The inspected unit-test tree has an arithmetic smoke and storage-move tests;
these are **definitions inspected, not tests run**, and neither proves the
lifecycle contracts above. Useful future device test candidates are same-config
reentry before/after grace, changed resolution/bind scope, forced restart,
wrong-model and same-model delayed stop, cancellation followed by retry, and
host shutdown with observed sockets. Each needs an authorized native setup;
none is reported as a passing test here.

Excluded: full Compose UI and navigation analysis, all Android OS interleavings,
network penetration/security certification, native cancellation implementation,
model import/download validation, full storage-move implementation, image decode
and history persistence, model quality, memory-fit and performance experiments.
