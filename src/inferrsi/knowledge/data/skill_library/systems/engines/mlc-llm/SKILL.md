---
name: mlc-llm
description: "Investigate MLC LLM compiled Metal artifact/schema, Apple target and pinned TVM module/storage/stream contracts, and compile/runtime KV limits without confusing canonical metadata, codegen or automatic estimates with runnable native model qualification."
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
        "mlc-llm",
        "tvm",
        "metal",
        "artifact-contract",
        "target",
        "sdk",
        "module",
        "stream",
        "kv-cache",
        "compiled-limits"
      ],
      "sources": [
        {
          "type": "git",
          "url": "https://github.com/mlc-ai/mlc-llm",
          "commit": "8978ea9aec626d64096aaa92fbc89bda2e3ea802",
          "license": "Apache-2.0 with retained NOTICE and source-specific component notices",
          "readset": "references/source-identity.json",
          "paths": [
            ".github/workflows/lint.yml",
            ".gitmodules",
            "CONTRIBUTORS.md",
            "LICENSE",
            "NOTICE",
            "README.md",
            "cpp/serve/config.cc",
            "cpp/serve/config.h",
            "docs/community/guideline.rst",
            "docs/compilation/model_artifact_manifest.rst",
            "pyproject.toml",
            "python/mlc_llm/__init__.py",
            "python/mlc_llm/base.py",
            "python/mlc_llm/compiler_pass/dispatch_kv_cache_creation.py",
            "python/mlc_llm/interface/compile.py",
            "python/mlc_llm/interface/convert_weight.py",
            "python/mlc_llm/interface/gen_config.py",
            "python/mlc_llm/model/gemma4/gemma4_model.py",
            "python/mlc_llm/model/model.py",
            "python/mlc_llm/protocol/__init__.py",
            "python/mlc_llm/protocol/artifact_manifest.py",
            "python/mlc_llm/serve/__init__.py",
            "python/mlc_llm/serve/engine.py",
            "python/mlc_llm/support/auto_target.py",
            "tests/python/conftest.py",
            "tests/python/integration/test_model_compile.py",
            "tests/python/model/test_kv_cache.py",
            "tests/python/protocol/test_artifact_manifest.py",
            "tests/python/support/test_auto_target.py"
          ]
        },
        {
          "type": "git",
          "url": "https://github.com/mlc-ai/relax",
          "commit": "201fa0001c81431ccce05419b442c47779ea917c",
          "license": "Apache-2.0 with retained NOTICE and source-specific component notices",
          "readset": "references/source-identity.json",
          "paths": [
            "AGENTS.md",
            "LICENSE",
            "NOTICE",
            "src/backend/metal/codegen/codegen_metal.cc",
            "src/backend/metal/codegen/metal_fallback_module.cc",
            "src/backend/metal/codegen/metal_fallback_module.h",
            "src/backend/metal/runtime/metal_common.h",
            "src/backend/metal/runtime/metal_device_api.mm",
            "src/backend/metal/runtime/metal_module.mm",
            "tests/python/codegen/test_target_codegen_metal.py"
          ]
        }
      ],
      "applicability": {
        "scope": "Selected artifact/Apple target/pinned TVM Metal consumer and KV configuration source contracts. Common catalog categorization is not CPU inference or Apple qualification.",
        "prerequisites": "Access to the pinned MLC and exact TVM fork/gitlink contracts; native checks require separately prepared matching MLC/TVM/FFI and the applicable Apple SDK/device stack.",
        "input_contract": "MLC revision, TVM gitlink/build, model/tokenizer/quantized-parameter identity, target/host/SDK, compiled artifact/format, runtime device and the actual compiled/runtime configuration sources.",
        "produced_artifact": "An identity and actual-versus-declared boundary report for artifact, Metal runtime or KV-limit ownership, with a negative signal and smallest missing native discriminator.",
        "failure_modes": "Treating a schema hash as payload authentication, an opt-in WebLLM artifact contract as a native-engine ABI, serializable Metal fallback as runnable, or automatic capacity estimates as free memory can create unsupported qualification claims."
      },
      "limitations": [
        "Source-derived candidate; original compiled CPU/native tests, compiler/live API/CLI/model/Metal/fit/quality/service/performance execution not_run; required native BLOCKED_REQUIRED_BACKEND.",
        "Opt-in artifact manifest first targets WebLLM; native engine ignoring that ABI is not qualified by canonical metadata agreement.",
        "Serializable kind=metal fallback can be non-runnable; codegen/export/pipeline/submission and actual load/dispatch/completion differ.",
        "Helpers screen narrow explicit canonical metadata, literal target strings or limit clamping only; no general Pydantic/TVM emulation, actual tensor/weight/export authentication or GPU/memory simulation.",
        "Full model/tokenizer/quantization/VLM/RNN/speculation/disaggregation/CUDA/scheduler/dependency implementation and broad skill efficacy remain outside selected contracts.",
        "NO_LICENSE is unavailable machine SPDX metadata, not legal absence; both source owners Apache LICENSE/NOTICE bytes are independently retained."
      ],
      "provenance_readsets": [
        "references/repo-provenance.md",
        "references/source-identity.json"
      ],
      "consumption_mode": "packaged",
      "recommendations": [
        "Identify the interface's actual consumer before using a valid artifact manifest as evidence of native model/task support.",
        "Separate codegen/export from runtime factory/load, pipeline creation, dispatch and stream completion; a serializable kind=metal fallback can still be non-runnable.",
        "Trace runtime preference, compile-time bounds, nested workspace inputs and explicit overrides separately before interpreting a KV or working-set estimate."
      ]
    }
---

# MLC LLM compiled Metal and runtime contracts

Use this source-derived **candidate** for the boundary between model-package
metadata, compiled target artifacts and real native runtime behavior. Begin
with [source identity](references/repo-provenance.md). MLC and its exact TVM
fork/gitlink are separate source owners; an arbitrary newer TVM is not an
interchangeable implementation.

## Route by the failed contract

| Question | Canonical owner |
| --- | --- |
| Do normalized tasks, parameter schema, executor/adapter roles and parameter-only resources agree? | [artifact-contract](sub-skills/artifact-contract/SKILL.md) |
| Do target/host/SDK/suffix/prefix, payload format, runnable module and selected storage/stream agree? | [metal-build-runtime](sub-skills/metal-build-runtime/SKILL.md) |
| Which compiled/runtime limit or workspace input is actually controlling the KV path? | [runtime-kv-limits](sub-skills/runtime-kv-limits/SKILL.md) |
| What remains outside these source contracts, including rights and native evidence? | [scope and notices](references/scope-and-notices.md) |

## Establish the actual boundary

1. Record MLC revision, TVM gitlink/build, model/tokenizer/quantized parameter
   identity, target/host/SDK, compiled artifact/format and runtime device. A
   canonical interface or parameter-schema hash does not hash tensor bytes,
   authenticate exports, select a device or prove native consumer support.
2. Identify which consumer implements the interface. The inspected artifact
   manifest is **opt-in**, first consumed by WebLLM. The native engine does not
   consume that contract at this pin; a valid sidecar cannot imply native
   support for its model/task ABI.
3. Separate metadata checks, IR/codegen, serialization/export, real runtime
   factory/load, pipeline creation, dispatch, stream completion, numerical
   behavior and model/service results. Each requires distinct evidence. A
   serializable kind=metal fallback is explicitly non-runnable.
4. Follow actual compiled metadata and configuration sources. Runtime preference,
   compile-time bound, nested workspace shape and explicit engine override are
   different values. The Metal working-set attribute and automatic-capacity
   constants do not establish free memory, safe allocation or universal limits.
5. Use only the selected bundled standard-library helper on explicit synthetic
   or anonymized declarations. Helpers do not import MLC/TVM, run Pydantic,
   initialize submodules, inspect weights/binaries, invoke a compiler or probe a
   device. Their narrow domains are not complete upstream input validators.

## Native preparation and evidence limits

The source pyproject declares 0.20.0.dev0; no installed package/build is implied.
MLC's native Python package loads TVM/serving integration, and original artifact
tests also import TVM DataType/model definitions and Pydantic. Even apparently
pure schema/codegen/IR tests require the actual prepared native stack. A
standalone Python declaration helper is not that stack or a passing source test.

This graph ships no installer, model-loading recipe or checkout-dependent source
test command. Compiler/native tests require separately prepared, version-matched
MLC/TVM/FFI dependencies and Apple SDK/device where applicable; broad compile or
integration loops can exercise many models and are not small default checks.
No compiler/live API/CLI/original source test or actual Metal/model execution is
claimed. Required native evidence remains `BLOCKED_REQUIRED_BACKEND / not_run`.

Return identities, actual versus declared facts, route/invariant, negative
signal and smallest missing native discriminator. Candidate empirical validation
is `not_run`. Helper, source hash, packaging or generic compile success does not
qualify cache correctness, physical fit, model quality, latency/service gains or
broad skill efficacy. No portable acceptance bar is derived from source test
constants or implementation crossover/capacity values.
