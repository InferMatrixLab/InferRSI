# InferRSI #714 Strata source replay

The replay covers the source-only Strata migration claimed in
[InferRSI #714](https://github.com/InferMatrixLab/InferRSI/issues/714#issuecomment-7237102878).

- Candidate base `70908f9705d4ed83f4fbad8de3b638001b8fec50`
- Implementation head `9d61fa82e92e0dd0169f5ac7ffdf6553e16eaad0`
- Implementation tree `46155489d145623b9bb5c54371b3f33d8facccc6`
- Published v0.3.4 source commit `e2f3be102c66c358803ed2186ed67bf627ebcbdf`
- Published v0.3.4 wheel SHA-256 `9a1015f2c1e1347f46d1ca899d2cb8e32c8279a75e88669b9de1a8c8bda5b6c9`

The old CLI ledger and 46 sets of raw stdout and stderr cover three package inventories,
42 successful L3 reads, and the rejection of an unpublished checkout. The Reader replay
covers the 13 added originals and the existing guide, 104459 original bytes in total.
The candidate result describes both fixed-source builds and the installed Reader's
ordered delivery, authorization and budget refusals, revision mismatch refusal,
and inventory boundary. The 107 old package identities and production CLI bindings
are tracked in the wider cutover.

Verify the ZIP against the adjacent `SHA256SUMS`. After extraction, the ZIP's own
`SHA256SUMS` lists the archived evidence files. The raw streams and ledger retain
the original authors, licenses, and source paths.
