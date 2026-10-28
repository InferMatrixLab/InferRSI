# Declared-limit helper contract

[audit_kv_limit_declarations.py](../scripts/audit_kv_limit_declarations.py)
provides `audit(plan)` and `example()`. It reproduces only selected clamp/minimum
rules on supplied declarations. It does not import the source, parse native
JSON, validate all engine overrides, inspect metadata/weights/devices or compute
allocation/capacity/performance.

Input is exactly `schema_version: 1` and `models`, a list of 1–64 objects. Each
model contains exactly:

- `name`: unique opaque ASCII letters/digits/underscore/dot/hyphen, 1–80 chars;
- `compiled_context`, `runtime_context`, `compiled_prefill`, `runtime_prefill`,
  `runtime_sliding_window`: positive integers or the explicit `-1` sentinel;
- `compiled_batch` and `workspace_prefill_from_compiled_config`: positive integers.

Integers are bounded to signed-64 maximum minus one, reserving native infinity
representation and rejecting booleans. This narrow helper domain is not a
claim that the source parser implements identical schema/bounds. The workspace
field denotes the nested compile-time input; it is not replaced by clamped
runtime prefill or authenticated by the helper.

Output reports each clamped runtime context/prefill, aggregate finite minima,
changed declarations and original workspace-prefill inputs. Null context or
sliding minimum means no finite bound in this selected rule, not infinite
capacity. Missing finite compiled/runtime prefill produces explicit source-limit
conflicts. Example aggregates: compiled/runtime context 4096, compiled prefill
512, runtime prefill 128, batch 8 and sliding 2048; workspace inputs remain
1024 and 512. Reducing runtime 128 to 32 changes its minimum, not those inputs.

`--example` prints synthetic input; file/stdin prints analysis. Valid supported
declarations return 0, declared source-prefill assertion conflicts return 1,
malformed input returns 2 with fixed diagnostics. Input is finite UTF-8 JSON
without duplicate keys, capped at 64 KiB. Deep/oversized/malformed input,
unknown/missing fields, invalid counts/types and known nonregular file paths
are rejected. A regular-file precheck is not an atomic hostile-filesystem guard.
Only stdout/stderr is written; no network/subprocess or native calls occur.

Every result keeps native/compiler `not_run`, input authentication and physical
fit `not_verified`, effective engine configuration and capacity estimate
`not_computed`. A helper success cannot qualify an engine, compiled cache or
model/service outcome. Use anonymized declarations, not private paths or data.
