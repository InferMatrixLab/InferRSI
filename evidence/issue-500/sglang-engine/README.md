# SGLang Engines verification for InferRSI #500

The migration of the SGLang source partition is pinned to `bf7fd0cd310c2d40414513871fb481fe1b63ac0d` on
`94238e7b4c3ea0dc9c7def1c8a879a5ae9308207`. The old wheel is InferRSI v0.3.4 at `e2f3be102c66c358803ed2186ed67bf627ebcbdf` with SHA-256
`9a1015f2c1e1347f46d1ca899d2cb8e32c8279a75e88669b9de1a8c8bda5b6c9`. [Original SGLang source](https://github.com/InferMatrixLab/InferRSI/tree/e2f3be102c66c358803ed2186ed67bf627ebcbdf/src/inferrsi/knowledge/data/skill_library/systems/engines/sglang)

- [Legacy CLI ledger](legacy-cli-ledger.json) records 28 actual calls with arguments, exit status, and stream sizes and digests. The archive contains all 56 stdout and stderr streams. The 15 original paths match the installed old wheel and pinned Git source byte for byte and total 105,972 bytes.
- The public checkout `checkout:audit-sglang-diffusion-lifetimes` preserves the legacy partial L1, its absent `validation` field, and its empirical `not_run` state. The ledger includes 69 relative links. The child checkout rejects the parent guide path that was readable under the old package identity. The checkout is Reader-only.
- [Installed Reader receipts](installed-reader-receipts.json) cover 19 cases for the checkout's L0–L3 responses, including exact-budget success, one byte short, refusal of each required item, and stale revision. Four further cases verify the 12 package-only atoms together through the Reader. Full legacy package composition remains part of #714.
- [Build result](build-result.json) records two builds with 3,027 byte-identical files, 1,313 catalog items, seven tasks, and 32 existing host entries. 421 scoped tests and Ruff passed.

Download [all raw receipts](sglang-engine-review-evidence.zip). The [SHA-256 manifest](SHA256SUMS) covers the archive and GitHub-readable files. The archive contains a manifest for each other member.
