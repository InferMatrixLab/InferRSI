---
name: mlc-llm
description: "Investigate MLC LLM compiled Metal artifact/schema, Apple target and pinned TVM module/storage/stream contracts, and compile/runtime KV limits without confusing canonical metadata, codegen or automatic estimates with runnable native model qualification."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
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
