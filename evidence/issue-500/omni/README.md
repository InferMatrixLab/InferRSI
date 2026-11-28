# InferRSI #714 Omni Engine source replay

The replay covers the source-only Omni Engine migration claimed in
[InferRSI #714](https://github.com/InferMatrixLab/InferRSI/issues/714#issuecomment-7237949284).

- Candidate base `70908f9705d4ed83f4fbad8de3b638001b8fec50`
- Implementation head `9e674573f75caba9afdfb285b2a5bd8c38d5df30`
- Implementation tree `d59be78f20fdf50e1610067b4ccd8091e7ca59d0`
- Published v0.3.4 source commit `e2f3be102c66c358803ed2186ed67bf627ebcbdf`
- Published v0.3.4 wheel SHA-256 `9a1015f2c1e1347f46d1ca899d2cb8e32c8279a75e88669b9de1a8c8bda5b6c9`

The old CLI ledger and 75 sets of raw stdout and stderr cover three package inventories,
69 successful L3 reads, two unpublished checkout identities, and an unrelated
checkout's authorization refusal. Each of the three packages returns every one
of the 23 original paths and exact contents.

The installed Reader group replay covers 21 added originals and two reused guides,
101031 original bytes in total. The candidate result describes both fixed-source
builds, ordered delivery, permission and budget refusals, a revision mismatch,
and the unchanged task and host inventories. The legacy package entry bindings
and production CLI remain part of the wider cutover.

Verify the ZIP against the adjacent `SHA256SUMS`. After extraction, the ZIP's own
`SHA256SUMS` lists the archived evidence files. The raw streams and ledger retain
the original authors, licenses, and source paths.
