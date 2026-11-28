# InferRSI #714 Local Dream checkout replay

The replay covers the Local Dream migration claimed in
[InferRSI #714](https://github.com/InferMatrixLab/InferRSI/issues/714#issuecomment-7241589971).

- Candidate base `2475ddb3bf06d62d1105c06979f8d68d34fd67bb`
- Implementation head `51fbcc621b26ae4eee2246f6a7ff9f208bc306e4`
- Implementation tree `6dea59988e844491907552b4cadf85077c7348ef`
- Published v0.3.4 source commit `e2f3be102c66c358803ed2186ed67bf627ebcbdf`
- Published v0.3.4 wheel SHA-256 `9a1015f2c1e1347f46d1ca899d2cb8e32c8279a75e88669b9de1a8c8bda5b6c9`

The legacy ledger and raw stdout and stderr cover 35 invocations of the released
CLI. They include the eight original paths, seven internal relative links,
both package callers, and checkout authorization examples. The 9,318-byte
native decision card retains its partial status, blocked backend, disabled
model, and absent validation field.

The installed candidate Reader replays the eight originals and exact ordered
L0–L3 bodies, applies each atom's permission and budget, and refuses stale
revisions. Both fixed-source builds produced the same 3,323 installed files
and generation. The existing model remains excluded from host export. The
two caller packages and external CLI consumption remain in the full cutover
scope.

The originals retain the accepted source and rights disclosures. The notice
scopes CC BY-NC 4.0 to upstream xororz/local-dream. AREX provenance is separate.
Review the [original rights decision](https://github.com/InferMatrixLab/InferRSI/blob/e2f3be102c66c358803ed2186ed67bf627ebcbdf/docs/reviews/local-dream-repo-to-skill.md)
alongside the raw receipts.

Verify the ZIP against the adjacent `SHA256SUMS`. The ZIP also carries a
`SHA256SUMS` file for every archived receipt, result and ledger.
