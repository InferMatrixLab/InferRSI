# Retrieval input proposal — not an activated acceptance freeze

CPU-only job1964 completed0 in28 seconds, with30 exact-length inputs and2,048,000
tokens in total. Inputs use the authenticated official tokenizer/chat template
and thinking disabled. At each of8192/65536/131072 tokens,10 distinct cases each
contain four independent key/value targets near10/35/65/90 percent of absolute
input token positions. The recorded starts include the newline preceding each
record. Synthetic decoys are deterministically generated; no private corpus.

Every target key appears exactly twice in the decoded prompt (record and query);
every target value appears once. The exact needle slices decode to their stated
record text. The generated archive is compressed losslessly with deterministic
gzip metadata; manifest records both compressed and uncompressed SHA256 plus
per-case input hashes, positions, expected answers and tokenizer identities.
The local readback independently authenticated all30 records, lengths, hashes,
manifest correspondence and positions. This is preparation, not retrieval
accuracy or model execution. The generator is retained unchanged under
validator/diagnostics/prepare_retrieval.py.

Extraction is predeclared in metadata.json: strip surrounding whitespace;
optionally unwrap a single enclosing lowercase `json` code fence; parse the
entire remainder as JSON; reject duplicate keys, missing/extra keys and nonstring
values. Score exact expected strings, without case folding or substring matching.
Report complete-case accuracy and each position. The7 local extraction checks
cover exact object, permitted fence, duplicates, extra keys, wrong case, invalid
JSON and nonobject output.

No answers have been observed at input preparation. Baseline qualification and
owner approval precede any activation; no regeneration based on model mistakes.
The9/10 baseline proposal and candidate nonregression gate remain owner-review
drafts from plan/freeze-proposal.md. No final-set candidate tuning is authorized.

Disposition before any model answers: independent review rejected this version
for freezing because targets differ in format and decoys repeat. See sibling
retrieval-proposal-v2 for the revised inputs; original bytes are retained.

Publication layout: the generator output originally named `manifest.json` is
retained byte-for-byte as `metadata.json`. The existing bundle-sha256 schema
classifies and authenticates this metadata, compressed inputs and observer
sources through `plan/retrieval-integrity.json`; no validator schema or gate is
weakened. Original remote artifacts retain their generated names.
