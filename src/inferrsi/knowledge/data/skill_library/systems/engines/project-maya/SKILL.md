---
name: project-maya
description: "Investigate Project Maya model-family dispatch, representation and memory tiers, API versus native state, speculative decoding and source-qualified verification without treating safe CPU checks as CUDA/HIP or model evidence."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
---

# Project Maya inference engineering

Use this source-derived **candidate** for model-specific inference questions in
`mw00/project-maya`. Read [source and method provenance](references/repo-provenance.md)
first. It is neither a generic model loader nor a verified inference engine.
The bundled helpers are offline support; reading this skill does not authorize
installation, engine startup, model downloads, GPU/API calls or host changes.

## Route by the failing contract

| Question | Canonical procedure |
| --- | --- |
| Which model family/format, architecture guard, physical memory pool or residency tier? | [model-runtime](sub-skills/model-runtime/SKILL.md) |
| API continuation, ownership, native slots, images, parallel state, cancellation or recovery? | [serving-state](sub-skills/serving-state/SKILL.md) |
| Draft selection, rollback, calibration, quantization quality, benchmark or evidence level? | [qualification](sub-skills/qualification/SKILL.md) |
| Build/setup side effects, missing tools or dependency/license ambiguity? | [troubleshooting](references/troubleshooting.md) and [license boundaries](references/license-boundaries.md) |

The retained snapshot has GLM, DeepSeek and MiniMax operating paths plus a newly
documented Qwen route. Coverage is intentionally asymmetric: selected core/state/
qualification bodies for the first three, shallow dispatch/format/guard evidence
for Qwen. Unmined deep kernels and unexecuted native/model paths stay explicit;
source presence or a common Python facade is not cross-family qualification.

## Establish identity before changing a setting

1. Record the full source revision, actual executable/family, model and asset
   identities, representation, compiler/runtime/device, full rendered workload,
   sampling policy and active single/parallel route. A release label, common
   quant tier name or nominal bit width is insufficient.
2. Distinguish caller-supplied metadata from inspected bytes and executed results.
   Root MIT notices do not license every optional model asset; source code,
   weights, drafts, fonts and UI components have separate boundaries.
3. Identify the state/resource owner and lifetime. Shared weights are not private
   conversation state; API history is not native KV; unified physical memory
   must not be counted independently as both RAM and VRAM.
4. Select the relevant route, its local helper and its stop conditions. Preserve
   exact tokens/image identity and completion boundaries before attempting reuse
   or tuning. Never repair a slot header merely to make it appear compatible.
5. State a falsifiable hypothesis and the smallest safe check. A policy arithmetic
   result, simulated decision or request JSON can guide an investigation but
   cannot authenticate a model payload, actual fit, GPU cleanup or speedup.
6. For a native change, freeze correctness and comparison requirements before
   experiments, retain failures/negative observations, and distinguish component
   throughput from complete service/quality outcomes. Do not transfer a source
   tuner margin into a portable campaign acceptance bar.

## Return a bounded conclusion

Report the route and identities, evidence class, invariant, proposed check,
actual result, counter-signal, missing resource and next authorized action.
When required CUDA/HIP/model evidence is unavailable, keep
`BLOCKED_REQUIRED_BACKEND` and an unverified/INCONCLUSIVE conclusion. Do not turn
exit-zero skips, CPU simulations, source reports or green scaffold CI into native
PASS. Model quality, E2E service behavior and broad skill efficacy need separate
validation. Native/backend flags remain unverified until separately established.

## Safe support and source boundaries

Each sub-skill owns a small bundled helper and detailed contract/troubleshooting
references. They are standard-library utilities, not model runners or copies of
unsafe setup/calibration scripts. Use their documented synthetic inputs; no
helper sends a request or installs dependencies. Source files are immutable
attribution links, not required runtime checkout paths. Keep this entire owner
folder when distributing it so the references, scripts and MIT notice remain.
