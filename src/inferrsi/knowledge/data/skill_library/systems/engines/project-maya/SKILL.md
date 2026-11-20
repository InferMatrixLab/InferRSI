---
name: project-maya
description: "Investigate Project Maya model-family dispatch, representation and memory tiers, API versus native state, speculative decoding and source-qualified verification without treating safe CPU checks as CUDA/HIP or model evidence."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
  inferrsi: |
    {
      "schema_version": 1,
      "kind": "skill",
      "origin": [
        "external"
      ],
      "status": "candidate",
      "empirical_validation": "partial_cpu_only",
      "license": "NO_LICENSE",
      "tags": [
        "project-maya",
        "model-specific-inference",
        "cuda",
        "rocm",
        "expert-tiering",
        "native-state",
        "speculation",
        "evidence-boundaries"
      ],
      "sources": [
        {
          "type": "git",
          "url": "https://github.com/mw00/project-maya",
          "commit": "249f9a87d1a9d72bec2b684d704b0aa9296b1c9c",
          "version": "VERSION1.1.34; CMake0.1.27 differs",
          "license": "MIT (root source); model/optional assets separate",
          "readset": "references/source-identity.json",
          "paths": [
            "CMakeLists.txt",
            "LICENSE",
            "LICENSE.deepseek-v41",
            "LICENSE.minimax-m31",
            "LICENSE.qwen-community-1.0",
            "README.md",
            "VERSION",
            "bench/results/2026-10-06-glm-spec/README.md",
            "bench/results/MAYA-S.md",
            "docs/MODELS.md",
            "docs/RESPONSES.md",
            "docs/SETTINGS.md",
            "include/strata/core/glm_model.hpp",
            "include/strata/core/mtp_rows.hpp",
            "include/strata/program/conv_cache.hpp",
            "include/strata/spec/controller.hpp",
            "include/strata/spec/draft_policy.hpp",
            "include/strata/spec/suffix_drafter.hpp",
            "maya.py",
            "maya.sh",
            "serve/response_config.py",
            "serve/response_jobs.py",
            "serve/response_schema.py",
            "serve/response_store.py",
            "serve/responses.py",
            "serve/server.py",
            "serve/test_response_jobs.py",
            "serve/test_response_store.py",
            "serve/test_responses.py",
            "setup.py",
            "setup.sh",
            "src/core/glm_fast_path.cu",
            "src/core/glm_memory.hpp",
            "src/core/glm_model.cu",
            "src/core/glm_mtp.cu",
            "src/core/glm_mtp_rows.cu",
            "src/core/glm_multi.cu",
            "src/core/glm_window.cu",
            "src/ds4/ds4_main.cpp",
            "src/ds4/ds4_model.cu",
            "src/ds4/ds4_model.hpp",
            "src/mm3/mm3_geo.hpp",
            "src/mm3/mm3_lane_plan.hpp",
            "src/mm3/mm3_main.cpp",
            "src/mm3/mm3_model.cu",
            "src/mm3/mm3_model.hpp",
            "src/mm3/mm3_pack.hpp",
            "src/mm3/mm3_sample.hpp",
            "src/program/conv_cache_test.cpp",
            "src/program/generate.cpp",
            "src/spec/controller.cpp",
            "src/spec/controller_test.cpp",
            "src/spec/draft_policy.cpp",
            "src/spec/draft_policy_test.cpp",
            "src/spec/suffix_drafter.cpp",
            "src/spec/suffix_drafter_test.cpp",
            "tests/core/mtp_rows_test.cpp",
            "tests/glm_memory_test.cpp",
            "tests/glm_pack_graph_test.cpp",
            "tests/glm_rows_attn_test.cu",
            "tests/glm_rows_kernels_test.cu",
            "tests/mm3_lane_plan_test.cpp",
            "third_party/beellama.cpp/LICENSE",
            "third_party/exllamav3/LICENSE",
            "third_party/ggml/LICENSE",
            "tools/calibrate_draft.py",
            "tools/calibrate_ds4.py",
            "tools/calibrate_ds4_tp.py",
            "tools/calibrate_glm.py",
            "tools/calibrate_mm3_prefill.py",
            "tools/ds4/pack.py",
            "tools/ds4/pack_gguf.py",
            "tools/exl3_pack.py",
            "tools/iq_pack.py",
            "tools/maya_names.py",
            "tools/maya_quant/kl_eval.py",
            "tools/maya_quants.py",
            "tools/mm3/calibrate.py",
            "tools/mm3/pack.py",
            "tools/mm3/pack_gguf.py",
            "tools/test_bench.py",
            "tools/test_calibrate_glm.py"
          ]
        },
        {
          "type": "git",
          "url": "https://github.com/VectorSpaceLab/AREX-Skill",
          "commit": "ac3fe1afa80fb9a09775ecfb2b6cc3ba850a2db6",
          "paths": [
            "cli/packages/coding-agent/src/disco/skills/create-repo-skill",
            "cli/packages/coding-agent/src/disco/skills/prepare-repo-skill-env",
            "cli/packages/coding-agent/src/disco/skills/workflow-authoring",
            "cli/packages/coding-agent/src/disco/skills/verify-repo-skill"
          ],
          "scope": "Compatible-agent portable native C++ adaptation, not DisCo CLI/model execution."
        }
      ],
      "construction": {
        "anchor_kind": "source",
        "distillation_form": "repository-operating-graph",
        "strategy": "arex-portable-meta-skills",
        "status": "partial-candidate",
        "native_import": "not-run",
        "method": "Stable-ID isolated author lanes, integrated runtime graph, assertion/helper/static and selected direct-compiler CPU verification; required accelerator/model blocks retained."
      },
      "applicability": {
        "scope": "Model-specific dispatch/residency, API/native state and qualification investigation. Common catalog placement is not CPU inference or cross-device certification.",
        "prerequisites": "Access to the selected model-family runtime/state/qualification contract; native changes need frozen correctness/comparison requirements and the matching authorized CUDA/HIP/model resources.",
        "input_contract": "Full source revision, actual executable/model family, model and asset identities, representation, compiler/runtime/device, rendered workload, sampling policy, single/parallel route, exact tokens/images and relevant completion observations.",
        "produced_artifact": "A route/identity/evidence-class report with invariant, proposed check, actual result, counter-signal, missing resource and next authorized action; missing native requirements remain INCONCLUSIVE.",
        "failure_modes": "Transferring coverage through a common facade or quantization name, confusing API history with native KV/private state, double-counting unified RAM/VRAM, or repairing a slot header to appear compatible can invalidate diagnosis.",
        "refusal_point": "When required CUDA/HIP/model evidence is unavailable, retain BLOCKED_REQUIRED_BACKEND and an unverified/INCONCLUSIVE conclusion; exit-zero skips or CPU simulations cannot clear it."
      },
      "limitations": [
        "BLOCKED_REQUIRED_BACKEND: no actual CUDA/HIP/model/device, quantized payload, vision, parallel/state/restore or cancellation-cleanup evidence.",
        "Safe CPU slices and offline helpers cannot establish complete engine builds, memory fit, numerical/model quality, service/performance or broad skill efficacy.",
        "Qwen coverage is shallow routing/format/guard evidence; its deep runtime/state/kernels remain unmined/unverified. Other family coverage is bounded rather than exhaustive.",
        "Source reports and source-specific calibration margins are not local measurements or portable acceptance gates.",
        "NO_LICENSE is the actual unauthenticated gh resolver fallback; root MIT is retained independently and optional/model asset licenses remain separate."
      ],
      "provenance_readsets": [
        "references/repo-provenance.md",
        "references/source-identity.json"
      ],
      "consumption_mode": "packaged",
      "recommendations": [
        "Select the family-specific route and preserve the explicitly shallow Qwen coverage rather than transferring deeper GLM/DeepSeek/MiniMax evidence.",
        "Separate shared weights, private conversation state, API history and native KV; count unified physical memory once.",
        "Preserve exact token/image identities and completion boundaries before reuse, then test one falsifiable hypothesis without modifying slot headers to bypass compatibility."
      ]
    }
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
