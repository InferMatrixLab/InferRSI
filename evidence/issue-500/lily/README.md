# Lily verification for InferRSI #500

The migration of `checkout:lily` is pinned to `bf9aa11080df6af3942a9ea9cffdbc085c4372e8` on
`0a764531cba2ea8bd2ce11aa8715d60b6f846358`. The old wheel is InferRSI v0.3.4 at `e2f3be102c66c358803ed2186ed67bf627ebcbdf` with SHA-256
`9a1015f2c1e1347f46d1ca899d2cb8e32c8279a75e88669b9de1a8c8bda5b6c9`. [Original Lily source](https://github.com/InferMatrixLab/InferRSI/tree/e2f3be102c66c358803ed2186ed67bf627ebcbdf/src/inferrsi/knowledge/data/skill_library/systems/engines/lily)

- [Legacy CLI ledger](legacy-cli-ledger.json) records 25 actual CLI calls with arguments, exit status, and raw stream sizes and digests. The archive includes all 50 stdout and stderr streams, including empty streams.
- All 18 originals match the installed v0.3.4 wheel and the pinned Git source by original path and exact bytes. Together they total 102,571 bytes. All 20 relative links have their original targets inside the directory. The legacy L1 remains partial with `validation` absent. The archived empirical status is `not_run`. The three Python helpers remain source-only.
- [Installed Reader receipts](installed-reader-receipts.json) cover exact-budget delivery, one byte short, authorization denial, and stale revision at each level. The 34 receipts use a single generation. L0, L1, L2, and L3 deliver 308, 6,701, 10,990, and 102,571 bytes respectively.
- The legacy public L1 decision card measures 7,987 bytes, and its CLI stdout is 10,066 bytes at the ordinary budget and 10,066 bytes at the exact card budget. The one-byte-short call returns a 622-byte stdout envelope without a card. The installed Reader's exact L1 budget is 6,701 source bytes, with a 1,067-byte canonical receipt. Reprojection yields the same legacy card. The public candidate CLI transport measurement is tracked in #715.
- [Build result](build-result.json) records two matching builds of 3,138 installed files with 1,348 catalog items, seven tasks, and 32 existing host entries. The migration passes 422 scoped tests and Ruff. The tests cover the legacy checkout and installed Reader. The four frozen guides retain `NO_LICENSE` and disable model invocation. The pinned upstream root `LICENSE` is Apache-2.0, with separate third-party notices. This checkout remains available through the Reader.

Download [the archive](lily-review-evidence.zip) to inspect the raw receipts. The [SHA-256 manifest](SHA256SUMS) covers the archive and the individual GitHub-readable files. The archive includes its own manifest for every other member.
