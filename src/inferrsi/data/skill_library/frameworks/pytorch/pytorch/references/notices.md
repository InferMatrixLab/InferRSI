# Attribution and license resolution

This graph distills [https://github.com/pytorch/pytorch](https://github.com/pytorch/pytorch) at `9a90a4fefcaafa63ac984621963a6fcc66aee68c`. The exact-ref GitHub license
query returned **NOASSERTION**; that value is preserved for the root and all
subskills rather than replacing it with an inferred SPDX identifier.

The upstream project metadata describes its main license as BSD-3-Clause and
declares a compound distribution expression for bundled components. Read the
retained [upstream LICENSE](../LICENSE) and [NOTICE](upstream-NOTICE) before
redistribution. Submodule/vendor licenses remain their owners' responsibility;
their unpopulated implementations are not copied into this graph. License
resolution is provenance, not a legal conclusion or verification result.

The Python helpers are original, bounded adaptations of cited public API,
documentation and test patterns. They do not copy the entire upstream test
harness, release automation or environment collector. Source relationships and
omitted side effects are in [script map](source-script-map.md). Copyright and
license notices for upstream material are retained unmodified as blob bytes.

AREX workflow contracts guided scope, evidence, construction and verification.
InferRSI local-skill-v1 owns packaging: name/quoted description are frontmatter;
license, disable-model-invocation and disco-role live in metadata.json. Literal
AREX frontmatter validation therefore needs an explicitly labeled temporary
projection; it cannot be described as a direct-final-tree validation pass.
