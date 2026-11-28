# InferRSI #714 ComfyUI checkout replay

The replay covers the ComfyUI migration claimed in
[InferRSI #714](https://github.com/InferMatrixLab/InferRSI/issues/714#issuecomment-7242714402).

- Candidate base `6842ae3436f03d4bd298c7f0ec43ca5aaec34dba`
- Implementation head `b28c4bc11cf38c7359bd6e0d80363e0eb33e9809`
- Implementation tree `c8e1fa7c2e941eed40fcd101e78a09f7dc452ac1`
- Published v0.3.4 source commit `e2f3be102c66c358803ed2186ed67bf627ebcbdf`
- Published v0.3.4 wheel SHA-256 `9a1015f2c1e1347f46d1ca899d2cb8e32c8279a75e88669b9de1a8c8bda5b6c9`

The legacy ledger and raw stdout and stderr cover 29 invocations of the
released v0.3.4 CLI. The checkout and two authorized package identities returned
six original files totaling 67,690 bytes, with four internal links. The legacy
partial decision card lacks validation. Candidate receipts separately cover the
Reader's ordered L0 through L3 groups, exact and short budgets, missing permission,
and stale revisions. The public CLI and installed package identity replay belong
to the cutover acceptance in #715.

Two independent fixed-source builds produced 3,343 byte-identical files.
The candidate adds the established ComfyUI checkout identity. The preserved
[original provenance](https://github.com/InferMatrixLab/InferRSI/blob/e2f3be102c66c358803ed2186ed67bf627ebcbdf/src/inferrsi/knowledge/data/skill_library/systems/engines/comfy-ui/references/repo-provenance.md)
pins Comfy-Org/ComfyUI b1a247c9 (0.42.0) and records GPL-3.0 scope with
separate AREX structure-only provenance and no upstream code vendored.

Verify the ZIP against the adjacent `SHA256SUMS`. The ZIP also carries a
`SHA256SUMS` file for every archived receipt, result and ledger.
