---
name: artifact-contract
description: "Screens MLC LLM normalized artifact declarations, canonical interface and parameter-schema hashes, executor and adapter links, export roles, and parameter-only resource limits without loading weights or compiled libraries."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
---

# Artifact Contract

Use this procedure when a model-package sidecar and a compiled program appear
incompatible, when public processor defaults affect an interface ID, or when a
parameter-size estimate is being mistaken for a device-capacity check.

This is source-derived candidate guidance for
[MLC LLM `8978ea9`](https://github.com/mlc-ai/mlc-llm/tree/8978ea9aec626d64096aaa92fbc89bda2e3ea802).
The bundled helper uses only Python's standard library. It does not import
MLC/TVM, inspect tensor bytes or binary exports, compile a program, or run Metal.
Native execution and compiler qualification remain `not_run`; required Apple
backend qualification remains `BLOCKED_REQUIRED_BACKEND`, not a CPU substitute.

## Choose the right boundary

- For hash payloads, defaults, processor representations and source ownership,
  read [contract mechanisms](references/contract-mechanisms.md).
- Before constructing input, read the exact
  [helper schema and limits](references/helper-contract.md).
- For malformed input, mismatched hashes, missing roles and deployment gaps,
  use [troubleshooting](references/troubleshooting.md).
- For Metal targeting, KV cache eligibility and runtime memory limits, continue
  with [runtime and KV limits](../runtime-kv-limits/SKILL.md). A manifest cannot
  answer those questions.

## Procedure

1. **Separate the two contracts.** `mlc-model-manifest.json` describes the model
   package; the compiled library's `_metadata.artifact` describes the program.
   Identify the public tasks, post-quantization parameter schema, and declared
   program roles independently. Do not substitute a chat-config filename,
   tokenizer checksum or weight-file size for either schema ID.
2. **Require normalized declarations.** Include supported processor defaults
   explicitly: audio `min_samples`, and prompt prefix/suffix arrays even when
   empty. Omit absent adapter/prompt fields; do not replace omission with null.
   The helper deliberately rejects non-normalized or unsupported input instead
   of reproducing Pydantic coercions or arbitrary TVM dtype behavior.
3. **Run the bundled declaration screen** from this directory:

   ```bash
   python scripts/audit_artifact_declarations.py --help
   python scripts/audit_artifact_declarations.py --example > declaration.json
   python scripts/audit_artifact_declarations.py declaration.json
   # The same explicit JSON can be supplied through stdin:
   python scripts/audit_artifact_declarations.py - < declaration.json
   ```

   The synthetic example is not a model package or a deployable compiled
   program. Edit only declarations you can substantiate. The helper reads one
   explicit regular file or stdin, writes JSON to stdout, and makes no network
   calls or persistent changes of its own.
4. **Interpret each result separately.** `interface_id` hashes normalized public
   tasks. `parameter_schema_id` hashes sorted name/shape/dtype records, not
   tensor contents. `metadata_consistent` reports only supported declaration
   checks. Fixed-code findings identify missing executor/adapter links,
   incomplete role pairs, invalid adapter-dtype references or supplied-ID
   mismatches. Exit zero means input was audited, not that findings are empty.
5. **Keep resource accounting narrow.** The maximum and sum cover parameter
   payloads only. Named dimensions affect byte estimates through declared
   `symbolic_sizes`, but their names remain in the parameter-schema hash.
   Exclude KV cache, temporary buffers, allocator overhead and runtime state
   from any conclusion based on these two numbers.
6. **Stop at metadata agreement.** Matching hashes do not prove weight integrity,
   symbol existence, argument ABI, feature support, memory fit or model quality.
   Manifest support is opt-in. The pinned source documentation identifies
   WebLLM as the first consumer and says native MLC backends ignore the manifest;
   do not infer native Gemma 4 or Metal support from a valid sidecar.

## Completion boundary

A useful result names the computed IDs, fixed findings, parameter-only byte
scope, unsupported declarations and remaining binary/backend questions. Keep
unknowns explicit. Original MLC protocol assertions and actual backend behavior
are separate from this portable declaration helper; neither is established by
its output.
