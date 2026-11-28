# DwarfStar verification for InferRSI #799

The migration of `checkout:dwarfstar` is pinned to `9bd7a3210df13694984d7c6c89a21f380e3f6adf` on
`2db3d83a29bf34ce14e883889d89a8373f3b6ad4`. The old wheel is InferRSI v0.3.4 at `e2f3be102c66c358803ed2186ed67bf627ebcbdf` with SHA-256
`9a1015f2c1e1347f46d1ca899d2cb8e32c8279a75e88669b9de1a8c8bda5b6c9`. [Original DwarfStar source](https://github.com/InferMatrixLab/InferRSI/tree/e2f3be102c66c358803ed2186ed67bf627ebcbdf/src/inferrsi/knowledge/data/skill_library/systems/engines/dwarfstar)

- [Legacy CLI ledger](legacy-cli-ledger.json) records 22 real CLI calls including their arguments, exit status, and raw stream sizes and digests. The archive contains all 44 original stdout and stderr streams, including empty streams.
- All 15 old originals match both the installed v0.3.4 wheel and the pinned Git source by original path and exact bytes. Together they total 78,171 bytes. All 16 internal links resolve within the selection. The legacy L1 is partial with `validation` absent and empirical status `partial_cpu_only`.
- [Installed Reader receipts](installed-reader-receipts.json) cover exact-budget delivery, one byte short, authorization denial, and stale revision at every level from L0 through L3. The 16 receipt cases use one installed generation. L0, L1, L2, and L3 deliver 335, 5,507, 10,103, and 78,171 bytes respectively.
- [Build result](build-result.json) records the pinned tree and two matching builds of 2,975 installed files, with 1,288 catalog items, seven tasks, and 32 existing host entries. The implementation passed 420 scoped tests and Ruff. The result covers knowledge retrieval and packaging. It makes no claim of live engine inference or added host exports.

Download [the archive](dwarfstar-review-evidence.zip) to inspect the raw receipts. The [published SHA-256 manifest](SHA256SUMS) covers the archive and the individual GitHub-readable files. Inside the archive, `SHA256SUMS` covers every other member.
