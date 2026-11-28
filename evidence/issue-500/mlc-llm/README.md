# MLC-LLM verification for InferRSI #500

The migration of `checkout:mlc-llm` is pinned to commit `168c42b5deeb6dceb9b1981734910d0331ab0b60` and tree
`2629a90075bdf199aa677b5ebe755093684b73ba` on the shared candidate `94238e7b4c3ea0dc9c7def1c8a879a5ae9308207`. The old wheel is InferRSI v0.3.4
at `e2f3be102c66c358803ed2186ed67bf627ebcbdf` with SHA-256
`9a1015f2c1e1347f46d1ca899d2cb8e32c8279a75e88669b9de1a8c8bda5b6c9`. [Original MLC-LLM source](https://github.com/InferMatrixLab/InferRSI/tree/e2f3be102c66c358803ed2186ed67bf627ebcbdf/src/inferrsi/knowledge/data/skill_library/systems/engines/mlc-llm)

- [Legacy CLI ledger](legacy-cli-ledger.json) records 34 actual CLI calls with arguments, exit status, and raw stream sizes and digests. The archive includes all 68 stdout and stderr streams, including empty streams.
- All 27 originals match the installed v0.3.4 wheel and the pinned Git source by original path and exact bytes. Together they total 129,248 bytes. All 36 relative links have their original targets inside the directory. The legacy L1 remains partial with `validation` absent. The archived empirical status is `not_run`. The three Python helpers remain source-only.
- [Installed Reader receipts](installed-reader-receipts.json) cover exact-budget delivery, one byte short, authorization denial, and stale revision at each level. The 43 cases include a separate denial for each of the 27 required L3 originals. L0, L1, L2, and L3 deliver 372, 6,206, 10,193, and 129,248 bytes respectively.
- [Build result](build-result.json) records two matching builds of 3,077 installed files with 1,326 catalog items, seven tasks, and 32 existing host entries. All 423 scoped atomic tests, the canonical consumer registry check, and repository Ruff passed. The runtime results cover the legacy checkout and the installed Reader.

Download [the archive](mlc-llm-review-evidence.zip) to inspect the raw receipts. The [SHA-256 manifest](SHA256SUMS) covers the archive and the individual GitHub-readable files. The archive includes its own manifest for every other member.
