# InferRSI #714 Flare Local Inference checkout replay

The replay covers the lifecycle checkout migration claimed in
[InferRSI #714](https://github.com/InferMatrixLab/InferRSI/issues/714#issuecomment-7243669645).

- Candidate base 022968d4bdda3cb4d1405b3199a24ad347cbca72
- Implementation head 9a8f93e0861694901e14965da6e76f76928b84c0
- Implementation tree 4527dcd552b27bb2b44e7b27fea5ae94b5fe144d
- Published v0.3.4 source commit e2f3be102c66c358803ed2186ed67bf627ebcbdf
- Published v0.3.4 wheel SHA-256 9a1015f2c1e1347f46d1ca899d2cb8e32c8279a75e88669b9de1a8c8bda5b6c9

The two legacy ledgers and raw stdout and stderr cover 29 checkout and package
invocations and eight cross-directory navigation invocations of the released
v0.3.4 CLI. The checkout and two authorized package identities returned six
original files totaling 54,873 bytes. The migrated originals retain nine
in-directory links and five cross-directory navigation links targeting four
files. The old checkout rejects direct reads of the external targets. Each
target is readable with its own legacy identity. Candidate proof covers the
checkout Reader's ordered L0 through L3 groups, exact and short budgets,
per-atom authorization, and stale revisions. The original public L1
decision card was partial and had no validation field. Its raw stdout is
included separately from the candidate Reader's selected section bytes.
Candidate public CLI and actual host navigation belong to #715.

Two independent fixed-source builds produced 3,432 byte-identical files.
The preserved
[original provenance](https://github.com/InferMatrixLab/InferRSI/blob/e2f3be102c66c358803ed2186ed67bf627ebcbdf/src/inferrsi/knowledge/data/skill_library/systems/engines/flare-local-inference/audit-flare-session-lifecycle/references/source-ledger.json)
pins NVIDIA/local-inference bce032c0 as source-only Apache-2.0 material and
records the AREX attribution separately.

Verify the ZIP against the adjacent SHA256SUMS. The ZIP carries a checksum
for every archived receipt, result and ledger.
