# InferRSI #714 vLLM base source replay

The replay covers the source-only vLLM base migration claimed in
[InferRSI #714](https://github.com/InferMatrixLab/InferRSI/issues/714#issuecomment-7238700601).

- Candidate base `70908f9705d4ed83f4fbad8de3b638001b8fec50`
- Implementation head `8678f10125cebb3659b4b2500af6c884a70806e6`
- Implementation tree `202de1eae2e3e8f4f42a7fccbc09ebf4f031402f`
- Published v0.3.4 source commit `e2f3be102c66c358803ed2186ed67bf627ebcbdf`
- Published v0.3.4 wheel SHA-256 `9a1015f2c1e1347f46d1ca899d2cb8e32c8279a75e88669b9de1a8c8bda5b6c9`

The old CLI ledger and 48 sets of raw stdout and stderr cover three package inventories,
42 successful L3 reads and three checkout authorization refusals. Each package
returns all 14 original paths, totalling 76,754 bytes.

The installed Reader group replay covers the 12 added originals and the reused
vLLM guide, totalling 73,493 bytes. The candidate result describes both fixed-source
builds, ordered delivery, permission and budget refusals and a revision mismatch.
The 3,261-byte repository provenance note is captured in the old ledger for separate
migration. Legacy package entry bindings and the production CLI remain cutover work.

Verify the ZIP against the adjacent `SHA256SUMS`. After extraction, the ZIP's own
`SHA256SUMS` lists the archived evidence files. The raw streams and ledger retain
the original authors, licenses, and source paths.
