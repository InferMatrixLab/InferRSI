# Mistral.rs verification for InferRSI #500

The migration of `checkout:mistral-rs` is pinned to `1c2ed7587c8c45c7a8576e1e944a5915dcd01c4a` on
`94238e7b4c3ea0dc9c7def1c8a879a5ae9308207`. The old wheel is InferRSI v0.3.4 at `e2f3be102c66c358803ed2186ed67bf627ebcbdf` with SHA-256
`9a1015f2c1e1347f46d1ca899d2cb8e32c8279a75e88669b9de1a8c8bda5b6c9`. [Original Mistral.rs source](https://github.com/InferMatrixLab/InferRSI/tree/e2f3be102c66c358803ed2186ed67bf627ebcbdf/src/inferrsi/knowledge/data/skill_library/systems/engines/mistral-rs)

- [Legacy CLI ledger](legacy-cli-ledger.json) records 31 actual CLI calls with arguments, exit status, and raw stream sizes and digests. The archive includes all 62 stdout and stderr streams, including empty streams.
- All 24 originals match the installed v0.3.4 wheel and the pinned Git source by original path and exact bytes. Together they total 118,734 bytes. All 31 relative links have their original targets inside the directory. The legacy L1 remains partial with `validation` absent. The archived empirical status is `not_run`. The three Python helpers remain source-only.
- [Installed Reader receipts](installed-reader-receipts.json) cover exact-budget delivery, one byte short, authorization denial, and stale revision at each level. The 40 receipts use a single generation. L0, L1, L2, and L3 deliver 362, 6,374, 10,788, and 118,734 bytes respectively.
- [Build result](build-result.json) records two matching builds of 3,068 installed files with 1,323 catalog items, seven tasks, and 32 existing host entries. The migration passes 420 scoped tests and Ruff. The tests cover the legacy checkout and installed Reader. The frozen guide disables automatic invocation. This checkout remains available through the Reader.

Download [the archive](mistral-rs-review-evidence.zip) to inspect the raw receipts. The [SHA-256 manifest](SHA256SUMS) covers the archive and the individual GitHub-readable files. The archive includes its own manifest for every other member.
