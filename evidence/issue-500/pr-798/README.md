# Husky migration review receipts for PR #798

These receipts cover [PR #798](https://github.com/InferMatrixLab/InferRSI/pull/798) at head 030415a087d1a305bfa294e246c5c4962ec47cb1, built from base 2db3d83a29bf34ce14e883889d89a8373f3b6ad4. The implementation tree is af1a5b9e0c69563f7172b312e412aafce041caa1.

## Released v0.3.4

The [v0.3.4 wheel](https://github.com/InferMatrixLab/InferRSI/releases/tag/v0.3.4) and [fixed source files](https://github.com/InferMatrixLab/InferRSI/tree/e2f3be102c66c358803ed2186ed67bf627ebcbdf/src/inferrsi/knowledge/data/skill_library/systems/engines/husky) match all seven originals by path and SHA-256. The [old CLI ledger](legacy-cli-ledger.json) contains arguments, exit codes and output digests for 16 native calls. Each of the seven resources is readable by `package:inferrsi.common.skills.husky` and `package:inferrsi.common.skills.audit_h3_runtime_residency` at their recorded revisions. Run `inferrsi` from an isolated v0.3.4 installation with the arguments in the ledger to replay a call.

The [discovery response](legacy-discovery.json) comes from `inferrsi find husky --kinds skill --limit 10 --decision-cards --no-external --json`. It ranks `checkout:husky` first and records the unavailable source. The old checkout read returns exit code 2 with “Document source requires URL and version or snapshot identity”. The unrelated `checkout:audit-h3-runtime-residency` also returns exit code 2 when asked to read the Husky guide outside its scope. The discovery file uses LF. Restoring CRLF gives the native stdout digest `46402bf4c5c0cdfd32efe008707742e96821752ec7e1420a1466c0ca50a5f91e`.

## Installed atomic Reader

[Installed Reader receipts](installed-reader-receipts.json) record two builds of the same generation with 2,937 identical files. The inventory digest covers the sorted map of relative file paths to SHA-256 hashes serialized as UTF-8 JSON with compact separators. The seven new L3 entries use package authority. The existing catalog entries and 104 host files match the base. No Husky checkout or host guide was generated.

The whole group delivers at exactly 22,586 body bytes. A one-byte shortfall, a denial of any tested operation (`read`, `retain`, or `redistribute`), and a stale revision each deliver zero bytes. The Reader receipts pin each source file and its full byte range. The exact implementation passed 418 atomic tests and full-repository Ruff checks.

[#715](https://github.com/InferMatrixLab/InferRSI/issues/715) tracks public CLI discovery, package caller authorization and the release cutover.
