---
name: splash
description: "Investigate Splash model-format compatibility, automatic memory planning, Metal and ANE execution, DFlash2 verification, cache and request identity, and correctness-gated serving measurements."
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
        "splash",
        "apple-silicon",
        "metal",
        "ane",
        "dflash2",
        "memory-plan",
        "prefix-cache",
        "persistent-cache"
      ],
      "sources": [
        {
          "type": "git",
          "url": "https://github.com/incoai/splash",
          "commit": "39a97385f8560cf8a93972cec9b0a963c9195250",
          "paths": [
            "README.md",
            "DEVELOPMENT.md",
            "docs/performance.md",
            "LICENSE",
            "THIRD_PARTY_NOTICES",
            "Makefile",
            "server/serve_options.py",
            "server/frontend.py",
            "server/lru.py",
            "server/protocol.py",
            "server/http_security.py",
            "server/origins.py",
            "server/runtime.py",
            "install/gguf.py",
            "runtime/engine/MemoryPlan.hpp",
            "runtime/engine/MemoryPlan.cpp",
            "runtime/engine/MemoryGovernor.cpp",
            "runtime/engine/MemoryControl.cpp",
            "runtime/engine/MemoryAudit.hpp",
            "runtime/engine/MemoryAudit.cpp",
            "runtime/engine/KvCache.hpp",
            "runtime/engine/KvCache.cpp",
            "runtime/engine/Cache.hpp",
            "runtime/engine/Cache.cpp",
            "runtime/engine/StateCache.hpp",
            "runtime/engine/StateCache.cpp",
            "runtime/engine/Scheduler.cpp",
            "runtime/engine/WriteBehind.hpp",
            "runtime/engine/WriteBehind.cpp",
            "runtime/engine/RuntimeResources.mm",
            "runtime/engine/Protocol.hpp",
            "runtime/engine/Protocol.cpp",
            "runtime/ops/DraftSelector.hpp",
            "runtime/ops/DraftSelector.cpp",
            "runtime/ops/Sampling.hpp",
            "runtime/ops/Sampling.cpp",
            "runtime/metal/kernels/decode/sampling.metal",
            "runtime/model/Runtime.hpp",
            "runtime/model/Runtime.cpp",
            "runtime/model/QwenState.cpp",
            "runtime/model/ModelDescriptor.mm",
            "runtime/model/DFlashDraft.hpp",
            "runtime/model/VerifyBudget.hpp",
            "dev/benchmarks/abba.py",
            "dev/benchmarks/backend_regression.py",
            "dev/benchmarks/logit_compare.py",
            "dev/benchmarks/http_regression.py",
            "dev/tests/server/test_serve_options.py",
            "dev/tests/server/test_lru_cache.py",
            "dev/tests/server/test_protocol_python.py",
            "dev/tests/tools/test_abba.py",
            "dev/tests/engine/engine_memory_plan_test.cpp",
            "dev/tests/engine/memory_audit_test.cpp"
          ],
          "license": "Apache-2.0",
          "readset": "references/source-identity.json"
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
          "scope": "Actual portable compatible-agent workflow with native/source-module adaptation, not DisCo CLI/model execution."
        }
      ],
      "construction": {
        "anchor_kind": "source",
        "distillation_form": "repository-operating-graph",
        "strategy": "arex-portable-meta-skills",
        "status": "partial-candidate",
        "native_import": "not-run",
        "method": "User-approved native Metal/C++ and isolated source-Python adaptation; stable-ID lanes, integrated graph, assertion cases and create/verify stages. Required-backend block disables automatic admission."
      },
      "applicability": {
        "scope": "Pinned Splash representation, planning, state/serving and verification investigation; common discovery does not qualify a different Mac/model/backend.",
        "prerequisites": "Access to the pinned representation/planning, serving-cache or qualification route; native checks need matching Apple/backend/model resources, an authorized workload and frozen semantic/measurement controls.",
        "input_contract": "Source/build, macOS/device, target and compatible draft artifacts/formats, tokenizer/template/vision selection, context/cache/memory controls, KV/recurrent precision, ANE and verifier-row policy, concurrency/priority/sampling, quality controls and cache state.",
        "produced_artifact": "An execution-identity report with observation, source-backed invariant, alternate explanation, smallest discriminating check, actual result and unresolved Metal/ANE/model/disk-state gap.",
        "failure_modes": "Treating an API alias as new weights, equal bit width as loader/kernel compatibility, or a fixed seed as fixed cache/batch/adaptive-verification scheduling can invalidate the comparison; CPU cache/codec checks do not prove GPU state.",
        "refusal_point": "Stop at unsupported formats, unavailable backend/model resources, unsafe service exposure or the authorized budget."
      },
      "limitations": [
        "Required Metal/ANE/model/actual device and disk-state execution remains BLOCKED_REQUIRED_BACKEND; Python policy/codec checks do not clear it.",
        "Service performance, quality, native recurrent-state recovery and skill efficacy remain unverified.",
        "Only selected bodies were mined; not all formats, kernels, supported devices or release/client workflows.",
        "NO_LICENSE is the actual unauthenticated GitHub CLI resolver fallback, not a legal conclusion; Apache-2.0 and third-party notices are retained."
      ],
      "provenance_readsets": [
        "references/repo-provenance.md",
        "references/source-identity.json"
      ],
      "consumption_mode": "packaged",
      "recommendations": [
        "Resolve representation, memory/cache owner, validity key and reclaim/rollback boundary before tuning a numeric control.",
        "Freeze semantic and workload controls beyond the seed, and retain actual-path fallbacks, admission waits, evictions, cancellations and errors.",
        "Inspect options without starting the normal serve path, which can download target/draft weights; installation and serving require separate task authority."
      ]
    }
---

# Splash inference engineering

Use this source-derived candidate to diagnose an inference or serving question,
select a bounded change and state the check that could falsify it. It is not a
complete upstream manual or a certified Apple backend recipe. Read
[source and method provenance](references/repo-provenance.md) before reuse.

## Route the work

| Question | Route | Expected result |
| --- | --- | --- |
| A format is rejected, a model will not fit or a cache cap is surprising | [runtime-planning](sub-skills/runtime-planning/SKILL.md) | Compatible representation and memory-owner ledger |
| Prefix reuse, persistent cache, request isolation or Responses history is confusing | [serving-cache](sub-skills/serving-cache/SKILL.md) | Identity, state-lifetime, admission and recovery ledger |
| Draft acceptance rises but speed/answers change; an ANE or precision path differs | [qualification](sub-skills/qualification/SKILL.md) | Semantic control, actual path and matching proof ladder |

Use the bundled [request builder](scripts/request_template.py) to prepare a
small Chat Completions body offline. It prints JSON; it never contacts a server,
installs Splash, launches a client or downloads a model. Its deliberately small
option set is not the complete upstream API.

## Establish the execution tuple

Record source/build revision, macOS and Apple device, target checkpoint/format/
quantization and artifact identity, compatible draft, tokenizer/template and
vision selection. Add context, cache/memory controls, KV and recurrent-state
precision, ANE setting, verifier-row policy, concurrency/priority, sampling,
prompt/output/quality controls and cold/warm/persistent-cache state.

An API model alias is not a new weight selection. Equal bit width does not
prove loader/kernel compatibility. A seeded request does not freeze cache,
batch/chunk or adaptive-verification scheduling.

## Native preparation boundary

The source targets Apple Silicon M3 or newer and macOS 26.4 or later. The public
release installation is `brew install incoai/tap/splash`; an authorized operator
can inspect `splash serve --help` before loading anything. Installation and
serving are separate actions: the normal serve path can download target/draft
weights. Do not run it solely to inspect an option.

Splash is a native Metal/C++ runtime with Python server/installer modules, not
a pip-installable project. This extraction adapted AREX's package inspection
to isolated, explicit source-module identity/signature checks. Linux Python
logic does not validate the actual Metal/ANE/model path.

## Work a bounded hypothesis

1. Read the selected route and nearest bundled mechanism/failure reference.
2. Separate source observation, upstream measurement and proposed experiment.
3. Identify representation, owner, validity key, lifetime and reclaim/rollback
   boundary before tuning a numeric control.
4. Freeze workload, semantic reference and measurement boundaries before a
   comparison. Keep campaign pins and gates in the acceptance issue.
5. Confirm the path actually activated; retain fallbacks, admission waits,
   evictions, cancellations and errors instead of treating them as warmup noise.
6. Correctness and model quality precede ranking. A cache/parser/codec check
   cannot establish GPU state, a distributional guarantee or service SLOs.

## Stop and report

Return execution identity, observation, source-backed invariant, alternate
explanation, smallest discriminating check, actual result and unresolved gap.
Stop at unsupported formats, unavailable backend/model resources, unsafe service
exposure or the authorized budget. Do not change system settings or launch an
external coding client merely because imported guidance mentions one.

Required Metal/ANE/model/actual disk-state evidence remains
**BLOCKED_REQUIRED_BACKEND**. Source and CPU checks do not qualify performance,
quality, service operation or behavioral skill efficacy. Final admission of a
partially verified candidate requires an informed decision, not auto-import.

The source [Apache-2.0 license](LICENSE) and
[third-party notices](THIRD_PARTY_NOTICES) are retained. `NO_LICENSE` is the
actual AREX resolver's unauthenticated-CLI warning fallback, not a legal finding;
models and external tools retain their own licenses.
