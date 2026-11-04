# Artifact contract troubleshooting

| Symptom | Likely distinction | Safe next action |
| --- | --- | --- |
| Exit 2 with fixed input diagnostic | Malformed JSON, unsupported declaration domain, file access, duplicate keys or a safety bound | Start from the bundled helper's `--example`; compare exact keys and types with the [schema](helper-contract.md). Do not expect paths or private values in diagnostics. |
| Hash differs after raw input reordering or removing defaults | Raw JSON was hashed instead of the normalized task representation | Restore explicit audio minimum and prompt prefix/suffix arrays; omit absent adapter/prompt. The helper does not perform Pydantic coercions. |
| `package_interface_id_mismatch` or `compiled_interface_id_mismatch` | Public tasks differ from the supplied identifier, or a declaration is stale | Compare processor kind/rate/resize/count, executor/output, prompt IDs and normalization. Export symbol changes alone are outside this hash. |
| Parameter-schema ID differs | Post-quantization names, shapes, dtypes or symbolic names differ | Compare schema records, not file sizes. Parameter order is irrelevant; duplicated names are rejected. Never rewrite an identifier merely to silence a mismatch. |
| Resource bytes change but parameter-schema ID stays constant | Named dimensions were resolved to different sizes | Compare `symbolic_sizes` and the configuration that substantiates them. This can be expected; it is not proof of identical actual weights. |
| Missing executor or adapter finding | Task links do not name declared program/adapters | Repair the declarations from the actual architecture contract. Matching IDs alone do not create the missing function or adapter. |
| Incomplete role-pair finding | Token and embedding roles were crossed, one half was omitted, or a second pair is partial | Declare at least one complete pair plus embed/cache roles; complete every additionally started pair. Check actual ABI separately. |
| Adapter-dtype reference finding | An override names an adapter not in that program | Remove a stale override or restore the real adapter declaration; do not invent a symbol. Empty override maps should be omitted. |
| Unsupported dtype, zero dimension or expression shape | Helper's narrow byte-aligned/positive/named-symbol domain was exceeded | Stop this resource calculation. Preserve the unknown and use the actual dtype/shape contract separately; do not approximate packed or vector storage. |
| Small parameter sum but allocation fails | KV cache, runtime scratch, state, alignment or memory pressure was excluded | Continue with [runtime/KV limits](../../runtime-kv-limits/SKILL.md). Do not increase a budget based only on manifest bytes. |
| Valid sidecar but native engine does not use it | Manifest is opt-in; frontend support differs | Check the [pinned compatibility boundary](contract-mechanisms.md). Do not infer native Gemma 4, audio or Metal support from a WebLLM-facing declaration. |
| Attempting to treat the helper as a package-import test | Metadata screening has no engine installation or native-library dependency | Use the bundled script without importing MLC/TVM. Compiler and native execution remain separate `not_run` qualifications. |

A negative metadata finding is useful without being an observed engine failure.
Conversely, empty findings do not verify binary exports, tensor contents or a
backend. Keep those unresolved rather than adding an automatic fallback or a
success claim that this helper cannot establish.
