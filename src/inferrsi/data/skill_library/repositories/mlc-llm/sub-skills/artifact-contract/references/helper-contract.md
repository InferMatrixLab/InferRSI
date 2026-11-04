# Declaration helper contract

## Entry and scope

Run [audit_artifact_declarations.py](../scripts/audit_artifact_declarations.py)
with Python 3.10 or later. It uses only the standard library and requires no
source checkout, MLC/TVM installation, compiler, model or GPU. Its APIs are
`audit(plan) -> dict` and `example() -> dict`; the latter returns fresh synthetic
input. Invalid or unsupported API input raises `DeclarationError`, a
`ValueError` subclass, without including caller values in its message.

Canonical JSON hashing and parameter-byte formulas are adapted from
[MLC LLM artifact_manifest.py](https://github.com/mlc-ai/mlc-llm/blob/8978ea9aec626d64096aaa92fbc89bda2e3ea802/python/mlc_llm/protocol/artifact_manifest.py#L279-L363).
The bundled filename is not an upstream MLC script. Its strict declaration
schema, validation bounds and findings are a portable adaptation, not the
original Pydantic models or a TVM dtype parser.

## Exact input object

All seven top-level keys are required; extra keys are rejected:

| Key | Value |
| --- | --- |
| `schema_version` | Integer `1`, not a boolean |
| `tasks` | Nonempty mapping of already-normalized public tasks |
| `programs` | Nonempty mapping of normalized program declarations |
| `parameters` | List of post-quantization name/shape/dtype records; may be empty |
| `symbolic_sizes` | Mapping from named dimensions to positive concrete integers |
| `required_features` | List of feature names; duplicates/order are permitted |
| `declared_ids` | Null, or the complete four-ID comparison object below |

Mapping names and nonempty symbol/name values are printable Unicode strings of
1–128 characters. Unicode is encoded as UTF-8 without normalization. Parameter
names, processor names and compiled symbols are declarations, not paths to open.
No values are resolved against files, imports, downloads or services.

### Tasks: explicit normalization only

Each task has exactly `executor`, `inputs`, `output`. Its nonempty input map
contains objects with `processor` and either both `adapter`/`prompt` or neither.
Null adapter/prompt fields are rejected. Supported processors:

- A nonempty string, for example `"tokenizer"`; no processor implementation is
  located or verified.
- Audio object with exactly `kind: "audio_decode"`, `format: "pcm_f32"`,
  `sample_rate_hz`, `channels: 1`, `min_samples`, `max_samples`. All numbers are
  positive integers; minimum must not exceed maximum. Explicit `min_samples`
  is required, even though the source parser can supply its default `1`.
- Image object with exactly `kind: "image_decode"`, `format: "rgb_u8"`,
  `layout: "nhwc"`, `resize`, `num_embeddings`. Resize has exactly `mode`
  (`stretch` or `center_crop`), positive integer `height` and `width`; embedding
  count is a positive integer.

Prompt objects have exactly `prefix_token_ids`, `placeholder_token_id`,
`suffix_token_ids`. IDs are nonnegative integers, never booleans. Prefix/suffix
are explicit arrays, including empty arrays, not omitted defaults.

### Programs and supplied IDs

Each program has exactly `kind`, `exports`, `adapters`, plus optional
`adapter_dtypes`. Exports is a nonempty role-to-symbol map; adapters may be
empty. When present, `adapter_dtypes` must be nonempty, reflecting the source
serializer's omission of empty overrides. Dtypes use the same narrow table as
parameters. An override naming a missing adapter is a consistency finding.

`declared_ids`, when non-null, has exactly:

- `package_interface_id`
- `compiled_interface_id`
- `package_parameter_schema_id`
- `compiled_parameter_schema_id`

Each value must be `sha256:` followed by 64 lowercase hex digits. Every supplied
ID is compared to its corresponding computed ID. Supplied IDs are not read from
a sidecar or binary, and agreement does not authenticate their origin.

### Parameters and resources

Each record has exactly `name`, `shape`, `dtype`. Names are unique. Shape is an
array of positive integers or named-symbol strings; an empty scalar shape
contains one element. Every symbol used in a shape needs a positive integer
value in `symbolic_sizes`. Extra declared size names are allowed but unused.

Only these byte-aligned storage dtypes are accepted:

| Dtype | Bytes per element |
| --- | ---: |
| `float16` | 2 |
| `float32` | 4 |
| `uint32` | 4 |

This deliberately small domain matches concrete original protocol fixtures; it
is not a source restriction on model dtypes. Packed quantization, vector lanes,
other float/integer types and symbolic expressions are unsupported, not declared
invalid in MLC. Dimensions, each multiplication, each parameter's bytes and the
aggregate sum must fit positive signed 64-bit arithmetic. Empty parameter lists
produce maximum/sum zero and the hash of an empty record list.

## Bounds and I/O

The helper accepts at most 64 KiB of UTF-8 JSON, depth 12 and 4096 tree nodes;
strings are additionally capped at 256 characters before schema-specific
limits. There may be at most 16 tasks, 16 inputs per task, 16 programs, 32 exports
per program, 16 adapters/overrides per program, 128 parameters, rank 8, 32 size
symbols, 32 features, and 128 IDs in each prompt prefix/suffix array. These are
helper safety bounds, not engine limits. API containers must be ordinary JSON
dicts/lists and values; floats, nonfinite values, coercions, duplicate CLI JSON
keys, booleans in integer fields and excess/unknown fields are rejected.

CLI accepts one optional positional regular file, `-` or omitted input for
stdin, `--help`, and `--example`. `--example` cannot be combined with a positional
input. It prints only synthetic input; pipe it to a separate audit invocation
if desired. Files are opened nonblocking where supported and checked as regular
files before reading; directories, FIFOs and special devices are rejected.
Diagnostics do not echo filenames, metadata values or exception tracebacks.

Exit `2` means invalid/unsupported declarations, JSON, arguments or input access.
Exit `0` means the audit completed, including when consistency findings exist.
No file is created or modified by the helper itself.

## Output interpretation

`interface_id` is the canonical hash of `{"tasks": tasks}`; accepted tasks are
already normalized. `parameter_schema_id` hashes records sorted by name, retaining
symbol names rather than their concrete resource values. Required features are
counted after sorted-set semantics; feature support is not probed and the helper
does not emit a deployable compiled artifact.

`metadata_consistent` means only that fixed-code `findings` is empty. Findings
cover missing executors/adapters, adapter-dtype references, required export roles,
incomplete role pairs and supplied-ID mismatches. They contain no caller names.
Resource maximum/sum describe parameter storage only. Output explicitly leaves
weight bytes unread, exports/ABI unverified, device features and fit unassessed,
and compiler/native execution `not_run`. Do not convert any of those fields into
a hardware, correctness, performance or service claim.
