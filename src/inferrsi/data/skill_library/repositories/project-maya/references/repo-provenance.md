# Source and method provenance

## Immutable source identity

- Canonical repository: [mw00/project-maya](https://github.com/mw00/project-maya).
- Inspected main snapshot: `249f9a87d1a9d72bec2b684d704b0aa9296b1c9c`, read2026-10-28.
- Tracked source checkout was clean. `VERSION` is1.1.34; the selected commit follows
  the release commit, rather than being asserted as an exact release tag.
- `CMakeLists.txt` still declares project0.1.27 and contains historical architecture
  comments. Preserve the full SHA and active branch/guard, not an inferred version
  or compatibility guarantee from a comment.
- The [bounded source inventory](source-identity.json) records retained evidence
  paths and SHA-256. A mined file does not imply every line/kernel was analyzed.

This refresh replaces the earlier read-only1.1.30 research snapshot, not an
existing Maya skill. New parallel routes, DS4 policy callsites and the Qwen
family were reread from the current source rather than inherited uncritically.
No change to the already-existing Strata owner is part of this distillation;
Strata attribution in Maya's own source license is retained.

## Actual construction method

[AREX-Skill](https://github.com/VectorSpaceLab/AREX-Skill/tree/ac3fe1afa80fb9a09775ecfb2b6cc3ba850a2db6)
portable create-repo-skill, prepare-repo-skill-env, workflow-authoring and
verify-repo-skill instructions informed compatible-agent orchestration: stable-ID
parallel lanes, root/whole-graph review, coverage and backend maps, then assertion,
helper/static and selected native CPU verification. This is not a DisCo CLI/model
API run, pip installation of Maya or managed DisCo import.

Maya is a C++20 CUDA/HIP engine family with Python launch/service tooling, not an
installable Python inference distribution. The explicit adaptation uses a
private standard-library inspection context and existing C++ compiler for tiny
selected policy tests, while complete engine builds and real backend/model
execution remain unavailable. No installer, large weight download, model/GPU/
paid-provider invocation or host/toolchain installation is part of the method.
The final reports, cases, environment and native results live outside this runtime
folder and do not become dependencies of the installed skill.

## Evidence and redistribution boundaries

The repository-license resolver actually ran for the exact source revision but
GitHub CLI was not authenticated: its result is `NO_LICENSE`, status unavailable.
Every root/sub-skill uses that same value. It is a warning, not a legal finding.
The independently inspected root [MIT notice](../LICENSE) preserves both Maya and
Strata contributors. [Asset/third-party boundaries](license-boundaries.md) remain
separate. No model payload, codebook, UI/font or vendored engine is bundled.

Source inspection, offline logic and partial native CPU checks do not establish
CUDA/HIP arithmetic, model/state fidelity, vision, parallel serving, persistent
restore, cancellation cleanup, quality/performance/service outcomes or efficacy.
The candidate remains backend-unverified and is not eligible for automatic
promotion based on missing required evidence.
