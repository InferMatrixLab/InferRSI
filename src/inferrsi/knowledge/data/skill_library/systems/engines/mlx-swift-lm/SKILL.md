---
name: mlx-swift-lm
description: "Investigate MLX Swift LM generation ownership, cancellation and settled task completion, and recurrent GatedDelta Metal versus ops contracts without confusing source predicates, final info or offline metadata with executed native correctness."
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
      "empirical_validation": "not_run",
      "license": "NO_LICENSE",
      "tags": [
        "mlx-swift-lm",
        "swift",
        "metal",
        "generation",
        "ownership",
        "cancellation",
        "task-join",
        "recurrent-state",
        "gated-delta",
        "native-evidence"
      ],
      "sources": [
        {
          "type": "git",
          "url": "https://github.com/ml-explore/mlx-swift-lm",
          "commit": "3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac",
          "version": "main 3.x API context; Swift tools 6.2",
          "license": "MIT; unselected vendored xgrammar separately Apache-2.0",
          "readset": "references/source-identity.json",
          "paths": [
            ".github/workflows/integration_tests.yml",
            ".github/workflows/pull_request.yml",
            "AGENTS.md",
            "CONTRIBUTING.md",
            "LICENSE",
            "Libraries/MLXLLM/Models/Qwen35.swift",
            "Libraries/MLXLLM/Models/Qwen3Next.swift",
            "Libraries/MLXLMCommon/Documentation.docc/upgrade.md",
            "Libraries/MLXLMCommon/Documentation.docc/using.md",
            "Libraries/MLXLMCommon/Evaluate.swift",
            "Libraries/MLXLMCommon/GatedDelta.swift",
            "Libraries/MLXLMCommon/KVCache.swift",
            "Libraries/MLXLMCommon/ModelContainer.swift",
            "Libraries/MLXLMCommon/ModelFactory.swift",
            "Libraries/MLXLMCommon/TokenLoopHandler.swift",
            "Libraries/MLXLMCommon/Tokenizer.swift",
            "Libraries/MLXLMCommon/UserInput.swift",
            "Libraries/MLXLMCommon/Utilities/GenerationWorker.swift",
            "Libraries/MLXLMCommon/Utilities/SerialAccessContainer.swift",
            "Libraries/MLXVLM/Models/Qwen35.swift",
            "Package.swift",
            "README.md",
            "Tests/MLXLMTests/CancellationTests.swift",
            "Tests/MLXLMTests/GatedDeltaQKNormTests.swift",
            "Tests/MLXLMTests/GatedDeltaTests.swift",
            "Tests/MLXLMTests/GenerationExecutionTests.swift",
            "Tests/MLXLMTests/Qwen35GDNDecodeBitwiseTests.swift",
            "Tests/MLXLMTests/Qwen35MTPTests.swift",
            "skills/mlx-swift-lm/SKILL.md",
            "skills/mlx-swift-lm/references/concurrency.md",
            "skills/mlx-swift-lm/references/generation.md",
            "skills/mlx-swift-lm/references/kv-cache.md",
            "skills/mlx-swift-lm/references/model-container.md",
            "skills/mlx-swift-lm/references/model-porting.md"
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
          "scope": "Actual portable compatible-agent source/native-Swift adaptation; no DisCo CLI/model run or managed installation."
        }
      ],
      "construction": {
        "anchor_kind": "source",
        "distillation_form": "repository-operating-graph",
        "strategy": "arex-portable-meta-skills",
        "status": "partial-candidate",
        "native_import": "not-run",
        "method": "Stable-ID lifecycle and recurrent-kernel author lanes, integrated root/local references, hard cases and offline support/static/scaffold/package checks; native Swift/Xcode/MLX compiler/tests not_run."
      },
      "applicability": {
        "scope": "Selected Swift ownership/cancellation/settling and actual GatedDelta Metal/ops contracts. Common categorization is not CPU inference or Apple qualification.",
        "prerequisites": "Access to the Swift lifecycle and selected GatedDelta contracts, with resolved MLX/native identities for a comparison; native checks require a prepared matching Swift/Xcode/Apple stack and separate authorization.",
        "input_contract": "Exact source revision, resolved Swift/MLX dependencies, Xcode/SDK/OS/device, API family and native artifact identity; the selected question supplies lifecycle ownership/completion observations or recurrent producer shape/dtype/layout and actual consumer/fallback.",
        "produced_artifact": "An identity and actual-versus-declared report for generation ownership or recurrent kernel invariants, with safe support result, counter-signal and smallest separately authorized native check.",
        "failure_modes": "Conflating lexical isolation with exclusive access across await or completed task join, treating useKernel as observed dispatch, calling an ops fallback CPU execution, or assuming a manifest range is a resolved dependency can invalidate the conclusion."
      },
      "limitations": [
        "BLOCKED_REQUIRED_BACKEND: native Swift/MLX compiler, host-control tests and required Apple Metal cancellation/backgrounding/kernel/cache/model/fit/quality/service/performance evidence not_run.",
        "Swift/Xcode/Apple SDK/MLX native stack unavailable; no live Swift API, package resolution, original source/native tests or CLI execution claimed.",
        "Helpers audit caller-declared evidence or selected metadata/byte/source-predicate contracts only; no tasks/recurrence/GPU simulation, authenticated observation, actual dispatch or numerical validation.",
        "Inspected masked kernel and ops output handling differ at source level; no masked-output native parity case executed, confirmed numeric bug or fix claimed.",
        "Full ChatSession/cache reconciliation, models/loading/quantization/VLM/tools/grammar/LoRA/training/FoundationModels and external MLX manager/provider internals are bounded gaps; broad skill efficacy unmeasured.",
        "NO_LICENSE is actual unauthenticated gh resolver fallback, not legal absence; root MIT retained independently."
      ],
      "provenance_readsets": [
        "references/repo-provenance.md",
        "references/source-identity.json"
      ],
      "consumption_mode": "packaged",
      "recommendations": [
        "Resolve mutable-context/cache ownership and task settlement separately from lexical isolation and queued GPU work before cache reuse or producer shutdown.",
        "Follow recurrent shape/dtype/layout to the actual Metal or ops consumer; predicate eligibility and useKernel alone do not prove dispatch.",
        "Record the actual dependency resolution and use the documented Xcode macOS test route; the source states swift test does not work for this package."
      ]
    }
---

# MLX Swift LM ownership and recurrent Metal contracts

Use this source-derived **candidate** for the Swift package's generation and
selected native recurrent-attention boundary. It is not a full model catalog,
a generic MLX tutorial or a verified engine. Begin with
[source and method identity](references/repo-provenance.md); source, resolved
MLX dependency, native artifacts and model assets are separate identities.

## Route by the broken contract

| Question | Canonical owner |
| --- | --- |
| Who owns mutable context/arrays/cache, what does cancellation stop, and has this producer actually settled? | [generation-lifecycle](sub-skills/generation-lifecycle/SKILL.md) |
| Does recurrent state/shape/dtype agree with the public GatedDelta gate and actual Metal/ops consumer? | [gated-delta-contract](sub-skills/gated-delta-contract/SKILL.md) |
| Which dependencies, model/runtime surfaces and rights remain outside this extraction? | [scope and notices](references/scope-and-notices.md) |

The package owns meaningful Swift concurrency and an embedded MSL recurrent
kernel, not merely an example invoking a foreign engine. Its MLX dependency
still owns array evaluation, custom-kernel binding and device/wired-memory
services. Do not invent those internals from a wrapper, or transfer Python
MLX-LM and other engines' cache/stream semantics without examining the caller.

## Establish identity and evidence before changing behavior

1. Record the exact source revision, resolved Swift/MLX dependencies, Xcode/SDK/
   OS/device, API family and native artifact identity. A manifest version range
   or a source release is not a resolved dependency or compiled artifact.
2. Separate lexical Swift isolation, exclusive access across await, ownership
   transfer, queued GPU work and completed task join. They are not synonyms.
   Select the lifecycle route before reusing a caller-owned cache or shutting
   down a producer after a consumer stops.
3. For recurrent kernels, follow producer shape/dtype/layout to the actual
   native consumer and fallback. A public predicate or `useKernel: true` is
   not observed dispatch; an ops fallback is not necessarily CPU execution.
4. Use the selected bundled helper with explicit synthetic/caller declarations.
   It does not import Swift/MLX, execute tasks or recurrence, authenticate
   observations, compile native code, load weights or simulate a device.
5. Retain negative signals, untested feature combinations and source-only
   discrepancies. Obtain separate authority and freeze controls/gates before
   any actual native, model, quality or service experiment. Source test-local
   tolerances and implementation constants are not portable acceptance bars.

## Preparation boundary

The inspected main branch documents the 3.x API line; its Package.swift requires
Swift tools 6.2 and declares platform minima macOS 14/iOS 17/tvOS 17/visionOS 1.
FoundationModels integration has distinct SDK/runtime availability constraints;
those minima do not qualify that adapter. MLX Swift is declared with
`.upToNextMinor(from: "0.33.0")`, and swift-syntax has a version range. There is
no tracked Package.resolved at this pin. Record the actual resolution before
native comparison rather than treating an observed tag as a lockfile.

This portable graph ships no installer or model-loading example. Use a
separately reviewed, authorized and versioned native preparation procedure;
do not run remote installers or fetch models/dependencies to read the skill.
The source explicitly says `swift test` does not work for this package; its
native route uses Xcode macOS testing. Source test fixtures and build steps are
not runtime dependencies of this packaged graph. Native execution plans stay
in external verification reports, not checkout-dependent helper commands.

Current inspection has no Swift/Xcode/Apple Metal stack. No live Swift API,
compiler, original native tests or CLI execution is claimed. The actual AREX
create/prepare/manual-workflow/verify adaptation is **partial source plus
offline support**, not a DisCo CLI/model run or managed skill installation.

## Return a bounded result

Report identities, actual versus declared facts, route/invariant, safe support
result, counter-signal and smallest next separately authorized native check.
Keep source inference, preparation, dispatch, numerical behavior, model quality
and client-observed service measurements distinct. Required native evidence
remains `BLOCKED_REQUIRED_BACKEND / not_run`; candidate empirical validation
is `not_run`. Packaging, independent content review and repository CI do not
promote the engine, establish physical fit, or prove comparative skill efficacy.
