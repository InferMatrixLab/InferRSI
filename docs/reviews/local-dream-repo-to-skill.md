# Local Dream portable repository-to-skill scope and verification

Governing accepted scope: [Issue 234](https://github.com/InferMatrixLab/InferRSI/issues/234).
Source is xororz/local-dream
`db162df4d9bb6efc6595250423d8df26241f4c27`; method source is AREX-Skill
`ac3fe1afa80fb9a09775ecfb2b6cc3ba850a2db6`. This report is construction and
validation context, not operating skill content or native execution evidence.

## Ownership and construction decisions

| Existing owner / possible overlap | Decision |
| --- | --- |
| stable-diffusion-cpp residency audit | Related diffusion lifetime concepts, but different source/fork/app/QNN/MNN and loader ownership; do not substitute its pin or controls |
| MLX Swift lifecycle / MLC artifact contracts | Similar declared-versus-executed distinction, not the Android service or DSP ABI implementation |
| `local-dream` | One registered common-discovery owner, router-like root, three deep references, explicit source/rights ledger, one original declaration-only helper |

No existing local-dream owner or duplicate Issue/PR was found at the assessed
main. Bounded reference authors inspected actual caller/consumer source; the
integrating author reconciled Android/native/packaging and evidence boundaries.
The source ledger bounds each readset. No unrelated six-repository distillation,
new runtime target, new primary matrix, CI lane or policy change is included.

AREX's source/test discovery → scoped extraction → backend classification →
construction → whole-owner integration → assertion/static/package verification
sequence is adapted to InferRSI. Local Dream has no Python distribution to
install, so no fictional installed API or pip success is reported. No DisCo CLI,
managed taxonomy/router import, approved native execution or full AREX
verification/import readiness is claimed. Candidate knowledge publication does
not waive a required backend gate.

## Depth, native candidates and smallest environment set

| Selected capability | Actual source / test candidate | Required backend and CPU substitution | Execution state / expected discriminator |
| --- | --- | --- | --- |
| Android desired/serving, quick reentry and forced restart | `BackendService.kt` and `ModelRunSupport.kt` consumer; no matching lifecycle test in the inspected two-file host-test tree | Android service + installed ARM64 native app/model; required; no full CPU substitution | `BLOCKED_REQUIRED_BACKEND / not_run`; observe ordered intents/process/health/full config and teardown across grace, changed resolution/bind and startup flags |
| Cancellation/upscale exclusion/cache/context transitions | `main.cpp`, actual Pipeline/PromptCache callers; proposed source-informed native cases, not named upstream passes | Selected Android MNN/QNN/Hexagon path and real model; required; no full CPU substitution | `BLOCKED_REQUIRED_BACKEND / not_run`; phase-aware cancel/retry and queue traces, cold/warm semantic checks, valid replacement publication and actual memory observations |
| DiT library/ABI/DSP packaging | Core/DiT CMake and build scripts, `DitEngine.h`, `PipelineDit` actual loader | Android SDK/NDK, matching SDKs/gitlinks/patches, ARM64 CPU and matching HTP device/model; required; none | `BLOCKED_REQUIRED_BACKEND / not_run`; inspect package CPU/DSP separation, actual symbol/ABI/create/dispatch/output/free stages |
| Host arithmetic unit smoke | `ExampleUnitTest.kt::addition_isCorrect` | JVM/JUnit with Android Gradle project prepared; alternative **only for arithmetic**; not lifecycle/native substitute | `not_run`; definition merely asserts 2+2=4 |
| Host storage move/journal regressions | `ModelStorageTest.kt`, including cross-mount copy, journal resume, same-size collision and partial-copy cases | JVM/JUnit and compatible project compilation; optional adjacent storage scope; not selected native substitute | `SKIP_NOT_SELECTED / not_run`; full ModelStorage implementation is not distilled or qualified |
| Offline declaration screen and complete knowledge delivery | Original helper plus InferRSI tests/readers/generators/wheel | Host Python standard library; full substitute only for **its own** exact-label comparisons and package-resource contract | Host checks only; do not relabel these upstream/native test passes or an efficacy trial |

The minimum **native** environment is a version-matched Android app/build stack
with actual selected MNN/QNN/Hexagon artifacts, model and supported device; DiT
also needs its separate Hexagon build/toolchain and DSP artifacts. A host Python
environment cannot satisfy it. Inspection found Java available, but no `adb`,
`cmake` or `ninja` command and no usable Android target in this execution scope.
No SDKs, submodules, weights or build dependencies were installed; no live
endpoint or model/native test was attempted. Absence of a command in this
environment is not an upstream support statement. Original Gradle test/build
and native CLI help are not executed and their task resolution is not claimed.

## Source script inventory

| Source artifact | Decision and reason | Bundled replacement / limit |
| --- | --- | --- |
| `app/src/main/cpp/build.sh`, `CMakeLists.txt`, `CMakePresets.json` | Reference-only: configure patches external QNN sample support, builds/stages SDK libraries and runtime assets; NDK/SDK specific | Packaging procedure, not a copied executable build wrapper |
| `app/src/main/cpp/dit/build.sh`, `dit/CMakeLists.txt` | Reference-only: patches dependency worktrees, compiles Hexagon/DSP artifacts, stages JNI/assets and removes older skels | Packaging procedure; no automatic SDK install or artifact writes |
| `gradlew` / `gradlew.bat` | Excluded execution wrapper: resolves Gradle/project/dependencies and can build/sign; no safe standalone contract check for selected native behavior | No copied wrapper; original stdlib declaration screen makes no Gradle call |
| Selected source tests | Reference-only test definitions, not runtime dependencies or passing tests | Six synthetic, source-informed assertion cases complement them; no claim that they replace native verification |

The helper is original narrow comparison logic, not adapted C++/Kotlin, a cache
format implementation, runtime simulation, device compatibility probe or model
validator. Every success output retains native `not_run` / `INCONCLUSIVE`.

## Verification and evaluation contract

`tests/test_local_dream_repo_to_skill.py` covers frontmatter/metadata/source
hashes, local-link containment, rights retention, fixture evidence paths,
all five configuration differences including bind scope, missing process,
ABI/SDK label mismatches, non-native outputs, strict types, duplicates/nonfinite
JSON, byte caps, private fixed errors and special-file/symlink rejection.
The six assertion cases live under
`tests/fixtures/repo_to_skill/local-dream/test-cases/`, with two difficult
cross-boundary integrations. They are structured reviewer rubrics, not observed
answers from a model trial. Complete source/static/packaging check commands and
their actual head-scoped results belong in the PR; generator output pins a real
published content revision.

Native validation and skill efficacy are **not evaluated**. A later authorized
bounded skill evaluation should freeze full reader-bundle revisions, sealed
cases, response schema, independent oracle, model/effort/order and budget before
N (no skill), E (complete exposed owner) and R (discovery) trials. Require the
oracle to reject Running=Ready, model-ID-only reuse, paired/authenticated LAN,
instantaneous cancellation/rollback, model-agnostic cache validity and equal
labels=native PASS. No paid calls or evaluation runner is invoked here.

## Rights and promotion limits

Pinned LICENSE bytes identify CC BY-NC 4.0 and are retained unchanged. Current
repository metadata's `NOASSERTION` is recorded separately, not fabricated as a
historical per-commit license response. No upstream code/assets/model/native
binaries are copied, and cataloging does not erase the NC restriction or grant
commercial compatibility. SDK/dependency/artifact rights remain separate.
Source knowledge is candidate; required native/model/quality/fit/thermal/service
and performance evidence is not_run / INCONCLUSIVE. Green scaffold CI or an
independent content review is not empirical promotion or campaign PASS.
