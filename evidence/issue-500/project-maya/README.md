# Project Maya verification for InferRSI #500

The migration of `checkout:project-maya` is pinned to `869eaf16168441dbc5d0102b9e87ea17c3a02506` on
`94238e7b4c3ea0dc9c7def1c8a879a5ae9308207`. The old wheel is InferRSI v0.3.4 at `e2f3be102c66c358803ed2186ed67bf627ebcbdf` with SHA-256
`9a1015f2c1e1347f46d1ca899d2cb8e32c8279a75e88669b9de1a8c8bda5b6c9`. [Original Project Maya source](https://github.com/InferMatrixLab/InferRSI/tree/e2f3be102c66c358803ed2186ed67bf627ebcbdf/src/inferrsi/knowledge/data/skill_library/systems/engines/project-maya)

- [Legacy CLI ledger](legacy-cli-ledger.json) records 28 actual CLI calls with arguments, exit status, and raw stream sizes and digests. The archive includes all 56 stdout and stderr streams, including empty streams.
- All 21 originals match the installed v0.3.4 wheel and the pinned Git source by original path and exact bytes. Together they total 131,250 bytes. All 27 relative links have their original targets inside the directory. The legacy L1 remains partial with `validation` absent. The archived empirical status is `partial_cpu_only`. The three Python helpers remain source-only.
- [Installed Reader receipts](installed-reader-receipts.json) cover exact-budget delivery, one byte short, authorization denial, and stale revision at each level. The 37 receipts use a single generation. L0, L1, L2, and L3 deliver 348, 8,333, 12,529, and 131,250 bytes respectively.
- [Build result](build-result.json) records two matching builds of 3,059 installed files with 1,320 catalog items, seven tasks, and 32 existing host entries. The migration passes 421 scoped tests and Ruff. The tests cover the legacy checkout and installed Reader. The four frozen guides retain `NO_LICENSE` and disable model invocation. The pinned upstream root `LICENSE` is MIT, with a separate attribution notice. This checkout remains available through the Reader.

Download [the archive](project-maya-review-evidence.zip) to inspect the raw receipts. The [SHA-256 manifest](SHA256SUMS) covers the archive and the individual GitHub-readable files. The archive includes its own manifest for every other member.
