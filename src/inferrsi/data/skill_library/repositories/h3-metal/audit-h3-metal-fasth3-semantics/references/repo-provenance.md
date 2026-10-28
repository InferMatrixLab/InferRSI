# Provenance and license boundaries

- Repository: [zuiho-kai/h3-metal](https://github.com/zuiho-kai/h3-metal).
- Source revision: `4ba47a3eabdbebf801ac6664b31f8ec168bc57a8`, main snapshot,
  inspected 2026-10-28, tracked checkout clean; tree
  `bedf4b65161f774c287f43ff4a7c2686f0ff2448`.
- Package/version: native C/Objective-C/Metal source, no Python distribution
  installed or live engine version verified. [Identity/readset](source-identity.json)
  records selected source bytes; no weights, remote headers or model config were
  downloaded for construction.
- Method: portable compatible-agent adaptation of AREX-Skill create/prepare/
  verify/extend workflows at
  [`ac3fe1afa80fb9a09775ecfb2b6cc3ba850a2db6`](https://github.com/VectorSpaceLab/AREX-Skill/tree/ac3fe1afa80fb9a09775ecfb2b6cc3ba850a2db6/cli/packages/coding-agent/src/disco/skills).
  InferRSI owns the procedure, metadata, catalog and installed resources. No
  DisCo CLI/model workflow, managed import or cross-agent export was run.
- Environment scope: source/static/stdlib CPU and InferRSI package delivery
  checks only. Required Apple/Metal/model tests are blocked/not_run, not replaced
  by CPU numerical mocks; missing native evidence prevents full qualification.

## Rights and machine resolution

The exact pinned [LICENSE](../LICENSE) is MIT, copyright 2026 Salvatore
Sanfilippo. [Third-party notices](THIRD_PARTY_NOTICES.md) retain the separate
BSD-3-Clause attribution for ccv-derived shader designs. No shader code is
bundled here. Source licensing does not license independent model weights,
exports, media, dependencies or external FastVideo material; those rights were
not newly resolved.

The inspected AREX license resolver attempted a read-only GitHub CLI query for
the same repository/revision on 2026-10-28. It returned `NO_LICENSE`, status
`unavailable`, reason `GitHub CLI is not authenticated`. That actual machine
fallback is preserved in metadata for workflow provenance, **not a
legal conclusion that source has no license**. It does not overwrite the
independently inspected MIT/BSD texts. No authentication or credential changes
were made. The check-only resolution record lives outside the runtime skill.

InferRSI's `local-skill-v1` contract places name/description in frontmatter and
structured fields, including license, in `metadata.json`; DisCo-only visibility
and managed-import fields are not imposed on this packaged destination.
