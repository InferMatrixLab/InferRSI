# Lithos Metal verification for InferRSI #500

The migration of `checkout:lithos-metal` is pinned to `15c83299a9ea5da02ff39d9d85dd4cf8d7d4b400` on
`94238e7b4c3ea0dc9c7def1c8a879a5ae9308207`. The baseline is the InferRSI v0.3.4 wheel at `e2f3be102c66c358803ed2186ed67bf627ebcbdf`
with SHA-256 `9a1015f2c1e1347f46d1ca899d2cb8e32c8279a75e88669b9de1a8c8bda5b6c9`.
[Original Lithos Metal source](https://github.com/InferMatrixLab/InferRSI/tree/e2f3be102c66c358803ed2186ed67bf627ebcbdf/src/inferrsi/knowledge/data/skill_library/systems/engines/lithos-metal)
[Migration claim](https://github.com/InferMatrixLab/InferRSI/issues/714#issuecomment-7234403668)

- The [legacy CLI ledger](legacy-cli-ledger.json) records 26 actual v0.3.4 calls with arguments, exit status, stream byte counts, and digests. The archive contains all 52 raw stdout and stderr streams, including empty streams.
- All 19 original paths and 100,455 bytes match the installed legacy wheel and pinned Git source. All 28 relative links retain their original targets inside the directory. The old L1 is a partial candidate card with `validation` absent and empirical status `not_run`.
- The [installed Reader receipts](installed-reader-receipts.json) cover exact-budget delivery, one byte short, authorization denial, and stale revision at each layer. Each of the 19 distinct required L3 roots was individually denied during the authorization checks. L0, L1, L2, and L3 deliver 269, 4,173, 9,215, and 100,455 bytes.
- The [build result](build-result.json) records two byte-identical builds with 3,053 installed files, 1,318 catalog items, seven tasks, and 32 existing host entries. All 421 scoped tests and the repository Ruff check passed. The old directory descriptor has no host export. The `package:inferrsi.common.skills.lithos_metal` caller is tracked in whole-library acceptance.

Download [the archive](lithos-metal-review-evidence.zip) for the raw receipts. The [SHA-256 manifest](SHA256SUMS) covers the archive and the individual files. A second manifest inside the archive covers its members.
