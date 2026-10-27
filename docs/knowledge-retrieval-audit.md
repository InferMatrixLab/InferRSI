# Knowledge retrieval audit

This audit covers the existing file-backed knowledge system and a bounded
manifest optimization. The [accepted scope](https://github.com/InferMatrixLab/InferRSI/issues/190)
owns the comparison protocol, revision pins and acceptance criteria. CPU
retrieval correctness and latency do not establish agent task quality, model
performance or an inference-service gain. Measurement results are pending the
independently frozen protocol and paired execution.

## Construction and ownership

Complete procedures live in
[`skill_library`](../src/inferrsi/data/skill_library/README.md): `SKILL.md`,
sidecar metadata, owner-local references, cases, scripts and licenses. The
registry maps stable names to categorized paths and backends.
[`build_skill_index.py`](../tools/build_skill_index.py) derives packaged JSON
abstracts and source-file hashes from those owners; it does not create another
editable procedure authority. Hand-maintained repository knowledge records
retain their own IDs, source revisions, applicability and verification limits.
[`catalog.py`](../src/inferrsi/catalog.py) validates and reads contribution,
dependency and peer records from their existing package-data directories.

| Axis | Meaning | Boundary |
| --- | --- | --- |
| Kind | `skill`, `knowledge`, `case` | Generated packaged skill abstracts are `knowledge`; checkout procedures are `skill` |
| Tier | `contribution`, `dependency`, `peer` | Repository relationship, independent of kind and empirical validity |
| Authority | `package`, `checkout`, `store` | Qualified identity ownership; collisions require explicit authority |
| Origin, state, applicability | Where guidance came from and where it may apply | Import or candidate state does not establish validation, permission or promotion |

[`KnowledgeReader`](../src/inferrsi/knowledge_operations.py) normalizes these
sources into complete Bundles. A package reader retains one catalog/library
snapshot. Checkout reads reload their current bytes; the optional
[`KnowledgeStore`](../src/inferrsi/knowledge_store.py) retains exact revisions in
an explicitly selected local SQLite workspace. Store writes publish candidate
bundles transactionally and do not edit the package or checkout.

A Bundle revision covers normalized metadata, every included resource hash and
resolved dependency revisions. Packaged records with `skill_documents` retain
the entire shared library as a conservative dependency closure. Returning a
small context therefore does not imply constructing a small Bundle. Reading
content never executes its procedure or scripts.

## Entrypoints and actual context delivery

| Entrypoint | Matching and ordering | Returned material |
| --- | --- | --- |
| `knowledge search` / `search_knowledge()` | All query tokens must occur in serialized catalog JSON; occurrence-count score, then ID | Catalog records; no complete Bundle construction |
| Default `collect()` | Whitespace-token AND substring matching over normalized metadata plus entrypoint; qualified identity order | Validated items; `material=True` adds the entrypoint body |
| `collect(relevance=...)` | Eligible generated packaged skills; distinct lexical words weighted by title, summary, tags/applicability and core; score then qualified ID | Same validated items; explicit IDs preserve caller membership/order |
| `collect(context_bytes=...)` | Mandatory complete core/references/readsets/licenses/notices, then optional complete owner resources ranked by cue or path | Separate exact-revision `contexts`, explicit omissions and UTF-8 body-byte accounting |
| `read()` / `resource()` | Explicit owner and optional/required exact revision | Complete Bundle view or selected exact resource bytes |

The merged [PR #129](https://github.com/InferMatrixLab/InferRSI/pull/129)
implemented the optional selection and context path; it is present in the
current source. The Python API returns context resources and omissions;
[`cli.py`](../src/inferrsi/cli.py) exposes `--relevance` and `--context-bytes`,
prints complete context bodies in text mode and returns the full envelope with
`--json`. `KnowledgeStore.collect()` delegates those same options to its reader.
An external agent must consume the returned material; these calls do not
automatically activate skills or execute a workflow.

For generated packaged skills, `material=True` still means `record.json`, not
the canonical `SKILL.md`. The latter is supplied through the optional context
view or exact resource access. Item limits and serialized `max_bytes` accounting
remain separate from context-body bytes. An oversized mandatory context is
omitted atomically; the selected item may still be returned.

The entrypoints are not interchangeable. The Python collect API supports
`repo`, `tier`, `backend` and `scenario`, but the current collect CLI parser and
dispatch do not expose them. The generator's README example
`inferrsi collect --repo-type inferrsi ...` consequently uses an unsupported
flag. This is a separate usability correction; this patch does not modify the
parser or regenerate catalog content.

## Redundant manifest work and the bounded change

Previously `Bundle.manifest()` hashed resource bytes during dependency
validation and again for its returned resource inventory. Directory
dependencies also rebuilt a sorted resource traversal. Required resource paths
were reparsed after the same content keys had already passed path validation.

The change creates one sorted resource digest map per manifest call, reuses it
for direct and directory dependency checks, and returns that same map. Present
string required paths reuse the earlier content validation; missing, unsafe
and malformed requirements retain their validation path. Nothing is cached
across calls: the frozen dataclass still contains mutable dictionaries, so each
manifest must observe changed metadata, bytes, resources and dependencies.

The remaining work is deliberate in this slice: each Bundle still validates
its complete closure, and collection still constructs eligible Bundles before
selection/output budgeting. Cross-Bundle caching, metadata-first indexes and
selection changes require their own mutation/identity contracts and evidence.

[`test_bundle_manifest.py`](../tests/test_bundle_manifest.py) compares the
manifest and revision with the complete digest formula, checks one resource
hash per manifest call, and exercises mutations, deletion, unsafe paths,
required resources and dependency revisions. Existing reader/selection/store
tests cover source drift, stale projections, checkout changes, budgets and
revision rejection. The paired CPU report must separately retain fresh/reused
reader results, CLI costs, exact output parity and all measured regressions.

## Quality limits and historical evidence

Less hashing cannot repair retrieval behavior. Default collect still has AND
substring matching and identity order. Optional relevance still uses literal
word overlap, positive-score eligibility and fixed field weights: it does not
resolve synonyms, infer task intent or provide calibrated no-answer confidence.
Whole-resource context can still exceed a budget, and callers still need to
follow omitted links through exact revisions. These are existing boundaries;
any observed misses or false positives must be reported with the measured cases.
No score, order, query, context budget or omission rule changes in this patch.

The closed [issue #128 owner report](https://github.com/InferMatrixLab/InferRSI/issues/128)
records accepted delivery of bounded whole-resource software and its comparison
packet: 36 attempts, 34 task PASS and 2 INCONCLUSIVE. It reports that C used
25.74% more input/output tokens than B, with no accepted reduced-cost/preserved-quality
benefit. Those are historical owner-reported results, not a rerun or new
independent verification by this audit. This work preserves that conclusion;
retrieval metrics and CPU parity cannot upgrade it to agent efficacy.
