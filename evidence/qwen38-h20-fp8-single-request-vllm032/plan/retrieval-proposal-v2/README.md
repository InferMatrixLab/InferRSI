# Revised retrieval proposal — unactivated, no model answers

Version1 is retained in the sibling directory and is not selected for freezing.
Independent reviewer review_fp8_graph found two shortcuts: decoys had different
identifier prefixes and an extra sentence;128 decoy records were repeated.
Version2 uses the same record template and identifier lengths for targets and
decoys, with unique deterministic decoy identities rather than a repeating pool.
All changes precede model answers; this is design review, not result-driven tuning.

CPU1965 prepared30 cases totaling2,048,000 tokens. Exact sizes and absolute
record start positions remain8192/65536/131072 ×10 and10/35/65/90 percent. The
same authenticated tokenizer and thinking-disabled chat template are used;
manifest binds the generator, inputs and tokenizer files. Target key/value
occurrence and needle-slice decode assertions all passed. Local compressed
readback independently authenticated all records, hashes, sizes and manifest
correspondence. Fixed positions, synthetic content and token-splice boundaries
still constrain generalization; this is not a universal long-context benchmark.

Extraction now distinguishes independent per-position matches from whole-object
validity. Complete-case success requires an exact four-key JSON object with
string values matching all expected values. Each position may match an available
string value even when another key is missing or an extra key occurs. Invalid
JSON or duplicate keys score all positions false. One enclosing lowercase `json`
fence is permitted. No normalization or substring matching. Eight focused local
cases check those rules. Version1's globally schema-conditioned scores are not
used for this proposal; neither version has been evaluated on model answers.

The prepared v2 observer accepts supported multi-token SSE deltas, validates
choice-event ITLs separately from usage-token counts, and requires one final
DONE. The pinned official client remains unchanged. Its source is retained but
has not run on a GPU. A separate prospective workload/cost declaration and
independent review precede baseline execution. The proposed9/10 qualification
and candidate nonregression gates still require owner confirmation.

Publication layout: the generator output originally named `manifest.json` is
retained byte-for-byte as `metadata.json`. The existing bundle-sha256 schema
classifies and authenticates this metadata, compressed inputs and observer
sources through `plan/retrieval-integrity.json`; no validator schema or gate is
weakened. Original remote artifacts retain their generated names.

Independent review of v2 found no blocking issue. A v3 observer successor makes
the intended CPU policy enforceable: assert no OMP_NUM_THREADS override before
launch, record the actual environment value, and let vLLM apply its default.
It also requests30 seconds for vLLM shutdown and allows45 seconds before observer
escalation. Wrapper unsets OMP explicitly; scorer/inputs/client/kernels unchanged.
All earlier observers remain immutable and unexecuted retrieval prototypes are
labelled as such. The added source snapshot increases inventory coverage to121.
Five original1961 raw streams satisfy the prospective v2/v3 validity expression,
including coalesced choices; five synthetic mutations (missing DONE, error event,
missing usage, wrong prompt and timing count) are rejected. That CPU check does
not change the original1961 job verdict. Eight local scorer boundary cases and
ten independent reviewer scorer cases passed. No retrieval GPU result yet.
