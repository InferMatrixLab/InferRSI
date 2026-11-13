# Artifact contract mechanisms

Read this before comparing IDs or deciding which artifact owns a mismatch.
All source links refer to MLC LLM commit
`8978ea9aec626d64096aaa92fbc89bda2e3ea802`; they identify provenance, not a
requirement for a local source checkout.

## Two documents and three distinct identities

The optional `mlc-model-manifest.json` uses schema `mlc.model-package`, version 1,
and fixed chat-config/weight-manifest filenames `mlc-chat-config.json` and
`tensor-cache.json`. The compiled half uses schema `mlc.compiled-program`,
version 1, inside library metadata. Models with no architecture-owned artifact
definition remain on the legacy path.

- `interface_id` identifies the normalized public task description.
- `parameter_schema_id` identifies post-quantization parameter names, shapes
  and dtypes; it is not a checksum of the weight values.
- Repository/compiler/dependency revisions and compiled-library bytes are
  separate identities. Neither schema hash attests to them.

Source: [contract models and versions](https://github.com/mlc-ai/mlc-llm/blob/8978ea9aec626d64096aaa92fbc89bda2e3ea802/python/mlc_llm/protocol/artifact_manifest.py#L139-L170),
[compiled artifact](https://github.com/mlc-ai/mlc-llm/blob/8978ea9aec626d64096aaa92fbc89bda2e3ea802/python/mlc_llm/protocol/artifact_manifest.py#L246-L276).

## Canonical task normalization precedes hashing

The source first validates each task through `TaskSpec` and sorts the task
mapping. Its interface payload is exactly `{"tasks": <normalized task mapping>}`,
where nested models are dumped with `exclude_none=True`. Canonical JSON uses
UTF-8, `ensure_ascii=False`, sorted keys and compact comma/colon separators;
SHA-256 is prefixed with `sha256:`. IDs contain exactly 64 lowercase hex digits.
No Unicode normalization is added. Ordering of mapping keys therefore does not
matter, but changing a represented processor value does.

Normalization is semantically important:

- A task names an executor, at least one input, and an output. The source checks
  nonempty executor/output strings.
- A processor is a nonempty name such as `tokenizer`, or a discriminated audio
  or image processor object. This layer does not resolve named processors.
- Audio means mono `pcm_f32`, positive sample rate and positive sample bounds,
  with minimum no larger than maximum. Omitted `min_samples` becomes `1`.
- Image means `rgb_u8`, `nhwc`, positive fixed height/width and embedding count;
  resize mode is `stretch` or `center_crop`.
- Adapter and prompt are declared together. Prompt token IDs are nonnegative;
  omitted prefix/suffix sequences normalize to empty arrays in JSON. Absent
  adapter/prompt values disappear from the hash payload rather than becoming
  literal null entries.

The helper accepts an explicitly normalized subset; it does not run Pydantic or
reproduce its input coercions. Hashing arbitrary raw JSON can give a different
ID even when the source parser would normalize it to the same task.

Source: [processor/prompt schemas](https://github.com/mlc-ai/mlc-llm/blob/8978ea9aec626d64096aaa92fbc89bda2e3ea802/python/mlc_llm/protocol/artifact_manifest.py#L37-L136),
[canonical serialization and interface ID](https://github.com/mlc-ai/mlc-llm/blob/8978ea9aec626d64096aaa92fbc89bda2e3ea802/python/mlc_llm/protocol/artifact_manifest.py#L279-L313).

## Parameters: schema names survive size resolution

The source creates records containing `name`, `shape` and stringified `dtype`,
rejects duplicate parameter names, and sorts by name. Each dimension becomes an
integer, an integer `.value`, a `.name`, or finally a string representation,
in that precedence. The canonical record list is hashed independently of
iteration order. The portable helper accepts only explicit positive integers
or named-symbol strings, never arbitrary object/stringification behavior.

Resource accounting resolves named dimensions using `symbolic_sizes`, computes
the product of dimensions times `TVM DataType.itemsize`, then takes the maximum
single-parameter bytes and the sum. For `embed: [vocab_size, 4], float16` and
`bias: [6], float32`, `vocab_size=10` yields maximum 80 and total 104 bytes.
Changing the size to 20 yields 160 and 184 bytes, but does not change the schema
hash: the record still contains `"vocab_size"`.

Both sizes exclude KV cache and runtime allocations. The source name
`estimated_device_memory_bytes` must not be interpreted as a complete process
or unified-memory footprint. Subbyte/vector dtype storage belongs to the real
TVM dtype contract, not an invented bits-divided-by-eight rule.

Source: [parameter normalization and resource formulas](https://github.com/mlc-ai/mlc-llm/blob/8978ea9aec626d64096aaa92fbc89bda2e3ea802/python/mlc_llm/protocol/artifact_manifest.py#L316-L363),
[resource scope](https://github.com/mlc-ai/mlc-llm/blob/8978ea9aec626d64096aaa92fbc89bda2e3ea802/python/mlc_llm/protocol/artifact_manifest.py#L239-L243).

## Executors, adapters and exports are declarations

Every task executor must name a compiled program. Every input adapter must be
in that program's adapter map. `adapter_dtypes` may override a declared
adapter's natural input dtype; the source validates it through TVM `DataType`
and omits the entire field when empty for frontend compatibility.

For `kind: token_generation`, exports require `embed_tokens` and
`create_kv_cache`, plus one or both complete pairs:

| Pair | Roles |
| --- | --- |
| Token-based | `prefill_tokens`, `decode_tokens` |
| Embedding-based | `prefill_embeds`, `decode_embeds` |

Declaring either member of an additional pair requires that pair's other
member too. A token prefill paired only with embedding decode is invalid.
Other nonempty kinds and additional role names are not globally forbidden by
these source validators. Nonempty symbol strings do not prove those functions
exist or take the claimed arguments. Programs, export symbols, dtype overrides,
resources and required features are outside the interface-ID hash.

Source: [program validation and serialization](https://github.com/mlc-ai/mlc-llm/blob/8978ea9aec626d64096aaa92fbc89bda2e3ea802/python/mlc_llm/protocol/artifact_manifest.py#L173-L236),
[cross-reference validation and feature deduplication](https://github.com/mlc-ai/mlc-llm/blob/8978ea9aec626d64096aaa92fbc89bda2e3ea802/python/mlc_llm/protocol/artifact_manifest.py#L394-L417).

## Production ownership and deployment limits

Compilation obtains tasks/programs from the architecture's `ArtifactDefinition`
and parameters from the quantized model export, then embeds the artifact in
metadata. Config generation emits the sidecar after quantized export. Weight
conversion compares an existing sidecar to the expected manifest before
replacing nearby weights; separate parameter-name/shape/dtype checks remain
necessary. This is not a weight-byte digest or an atomic-update guarantee.

The pinned documentation says WebLLM is the first manifest consumer; other MLC
backends read chat config and ignore the manifest. It also says the native
engine cannot yet serve Gemma 4 because it does not pass token IDs to the model.
Version 1 represents fixed-size image/audio inputs and text output, not dynamic
image grids, video, compressed/remote audio or native-server audio. These are
source-scoped limits, not a statement about later revisions.

Source: [compiler metadata ownership](https://github.com/mlc-ai/mlc-llm/blob/8978ea9aec626d64096aaa92fbc89bda2e3ea802/python/mlc_llm/interface/compile.py#L150-L217),
[conversion checks](https://github.com/mlc-ai/mlc-llm/blob/8978ea9aec626d64096aaa92fbc89bda2e3ea802/python/mlc_llm/interface/convert_weight.py#L195-L223),
[sidecar generation](https://github.com/mlc-ai/mlc-llm/blob/8978ea9aec626d64096aaa92fbc89bda2e3ea802/python/mlc_llm/interface/gen_config.py#L297-L306),
[documented compatibility and scope](https://github.com/mlc-ai/mlc-llm/blob/8978ea9aec626d64096aaa92fbc89bda2e3ea802/docs/compilation/model_artifact_manifest.rst#L188-L200).
