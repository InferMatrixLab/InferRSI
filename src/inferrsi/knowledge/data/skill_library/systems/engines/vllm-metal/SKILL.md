---
name: vllm-metal
description: "Investigate vllm-metal Apple inference through platform and native-ABI selection, paged KV/offload ownership, speculative/deferred state and actual dispatch/serving evidence without upgrading source or CPU checks to backend qualification."
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
        "vllm-metal",
        "apple-silicon",
        "mlx",
        "mps",
        "paged-kv",
        "kv-offload",
        "speculation",
        "deferred-execution",
        "evidence-boundaries"
      ],
      "sources": [
        {
          "type": "git",
          "url": "https://github.com/vllm-project/vllm-metal",
          "commit": "e7df7a6ff215f99c7842552d230fdbc709835934",
          "version": "0.32.0",
          "license": "Apache-2.0 (retained source); dependency/model assets separate",
          "readset": "references/source-identity.json",
          "paths": [
            "LICENSE",
            "README.md",
            "docs/CONTRIBUTING.md",
            "docs/benchmarking-macos.md",
            "docs/configuration.md",
            "docs/gqa-decode.md",
            "docs/installation.md",
            "docs/kv_offloading.md",
            "docs/pytorch-mps.md",
            "docs/speculative_decoding.md",
            "pyproject.toml",
            "scripts/lint.sh",
            "scripts/test.sh",
            "setup.py",
            "tests/conftest.py",
            "tests/test_config.py",
            "tests/test_envs.py",
            "tests/test_kv_offload_budget.py",
            "tests/test_kv_offload_tiering.py",
            "tests/test_kv_offload_worker.py",
            "tests/test_macos_defaults.py",
            "tools/avg_gen_length.py",
            "tools/native_sampling_probe.py",
            "vllm_metal/__init__.py",
            "vllm_metal/config.py",
            "vllm_metal/envs.py",
            "vllm_metal/metal/build.py",
            "vllm_metal/metal/paged_attention.cpp",
            "vllm_metal/platform.py",
            "vllm_metal/v1/cache_policy.py",
            "vllm_metal/v1/decode_pipeline.py",
            "vllm_metal/v1/kv_offload/config.py",
            "vllm_metal/v1/kv_offload/connector.py",
            "vllm_metal/v1/kv_offload/fs_tier.py",
            "vllm_metal/v1/kv_offload/shared_region.py",
            "vllm_metal/v1/kv_offload/spec.py",
            "vllm_metal/v1/kv_offload/worker.py",
            "vllm_metal/v1/model_lifecycle.py"
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
          "scope": "Compatible-agent portable source/Python partial adaptation, not DisCo CLI/model execution or managed import."
        }
      ],
      "construction": {
        "anchor_kind": "source",
        "distillation_form": "repository-operating-graph",
        "strategy": "arex-portable-meta-skills",
        "status": "partial-candidate",
        "native_import": "not-run",
        "method": "Stable-ID manual author sequencing plus bounded cache author lane; integrated graph followed by assertion/helper/static and selected pure Python source tests; Apple native blocks retained."
      },
      "applicability": {
        "scope": "Selected plugin preparation, KV/offload ownership and speculative/deferred/dispatch evidence investigation. Common catalog scope does not certify CPU inference or cross-backend qualification.",
        "prerequisites": "Access to the plugin-specific platform/ABI, cache-lifecycle and qualification contracts; actual engine changes require separate authority, resource ownership, frozen gates and cleanup, with a supported artifact pairing.",
        "input_contract": "Source/package/runtime/native artifact identities, Python/OS/chip/device, backend/executor, checkpoint/tokenizer/draft identities, format/dtype, effective feature flags and workload.",
        "produced_artifact": "An identity/route/invariant report with actual safe-check result, counter-signal and next authorized native check; partial CPU evidence stays separate from unverified transfers, sleep/wake, model and HTTP outcomes.",
        "failure_modes": "Using lazy import success as native registration or ABI evidence, treating a feature switch as dispatch, or conflating cache capacity with physical residency and kernel time with HTTP time can overstate plugin behavior."
      },
      "limitations": [
        "BLOCKED_REQUIRED_BACKEND: actual Apple MLX/Metal and MPS kernels/model loading, cache transfers/sleep/wake and real worker dispatch are not verified.",
        "Installed pure API inspection and selected parser/default tests do not establish a healthy inference dependency set: pip check failed missing requirements, a FastAPI mismatch and unsupported host platform.",
        "No model payload authentication, numerical/model quality, physical memory fit, HTTP service/performance or broad skill efficacy validation.",
        "Detailed GGUF/AWQ/quantization/MoE, DFlash/DSpark, multimodal, diffusion, STT/pooling/LoRA and distributed paths remain bounded route evidence or explicit long-tail gaps.",
        "NO_LICENSE is the actual unauthenticated gh resolver fallback, not legal absence; upstream Apache-2.0 LICENSE retained independently."
      ],
      "provenance_readsets": [
        "references/repo-provenance.md",
        "references/source-identity.json"
      ],
      "consumption_mode": "packaged",
      "recommendations": [
        "Resolve platform registration, backend/runner and native ABI pairing before capacity tuning; a package visibility check establishes only its reported software facts.",
        "Keep MLX and MPS, full-attention and recurrent state, logical cache capacity and physical residency as separate contracts.",
        "Preserve failed paths and distinguish parser/API checks from real transfers, sleep/wake, model output and HTTP performance evidence."
      ]
    }
---

# vLLM Metal inference investigation

Use this source-derived **candidate** for the vLLM Apple Silicon plugin, not
for generic vLLM, MLX or Metal programming. Read
[source/method provenance](references/repo-provenance.md) before applying it to
a checkout. This graph is self-contained operating guidance with offline
support; it does not include an inference engine or authorize executing one.

## Route by the contract that can fail

| Question | Owner |
| --- | --- |
| Why does import succeed but Metal registration/build/model selection fail? | [platform-config](sub-skills/platform-config/SKILL.md) |
| Why is a setting ignored, the runner wrong, or a native ABI stale? | Same owner; selected-knob syntax helper and preparation references |
| Does host offload add RAM, which prefix is reusable, or why does wake fail? | [cache-lifecycle](sub-skills/cache-lifecycle/SKILL.md) |
| Are GDN drafts rolled back correctly, pending tokens owned safely, or GQA actually executed? | [qualification](sub-skills/qualification/SKILL.md) |
| Can a reported rate/parity result support a service or quality claim? | Same owner; frozen workload, execution-boundary and failure accounting |
| What is covered, excluded or differently licensed? | [scope and notices](references/scope-and-notices.md) |

Upstream vLLM supplies API/scheduler/block management, mlx-lm model layers,
and this plugin the request-aware native attention/runtime integrations.
Shared upstream interfaces do not automatically qualify every combination.
The MLX path, alternative MPS path, full-attention versus recurrent state,
cache capacity versus physical residency, and kernel versus HTTP timing are
deliberately separate throughout these procedures.

## Establish identity and authority

1. Record exact source/package/runtime/native artifact identities, Python,
   OS/chip/device, backend and executor, checkpoint/tokenizer/draft identities,
   format/dtype, effective feature flags and workload. Readsets identify source
   bytes and selected analysis spans, not native execution.
2. Match the intended claim to its owner. Resolve an unsupported pairing or
   stale artifact before tuning capacity or quoting throughput. A feature
   switch permits eligibility; it does not prove that the worker took that path.
3. Choose the smallest safe check. The bundled helpers parse explicit JSON
   and compute bounded arithmetic/summaries, without native imports, downloads,
   services, credentials or host mutation. No helper authenticates model data,
   proves memory fit or measures inference.
4. Separate empirical facts, source reports, test definitions and proposals.
   Retain unsuccessful paths and missing evidence. A successful Python import
   or CPU parser test is not a native accelerator substitute.
5. For actual engine changes or experiments, establish separate authorization,
   safe resource ownership, frozen correctness/quality/performance gates and
   cleanup. Never erase a user KV store or install toolchains as an implicit
   step in answering a diagnostic question.

## Public preparation boundary

The source snapshot supports Python3.12/3.13 and requires Apple Silicon/macOS15+
for engine execution. Stable users can use the project's Homebrew tap/formula;
development source setup additionally builds native artifacts with full Xcode/
SDK26.2+. Installation is not performed by this skill. After an authorized
installation, a minimal read-only package check is:

```bash
python -I -c 'import importlib.metadata as m; import vllm_metal; print(m.version("vllm-metal"), vllm_metal.__version__)'
```

That deliberately lazy import proves only selected package visibility. Read
the platform route for exact ABI/backend/runner distinctions and failure
handling before a separately authorized startup. Do not execute remote shell
installers, upstream development scripts or model downloads from this graph.

## Return a bounded conclusion

Report identity, selected route, source-supported invariant, actual safe check,
result, counter-signal and smallest next authorized native check. This delivery
has partial CPU API/parser evidence only. Required Apple MLX/Metal and MPS
kernel/model, real transfers/sleep/wake, output quality, HTTP serving/performance
and broad skill efficacy remain unverified (`BLOCKED_REQUIRED_BACKEND` where
required). Source-derived candidate status is not promoted by packaging,
independent content review, a merged PR or green scaffold CI.
