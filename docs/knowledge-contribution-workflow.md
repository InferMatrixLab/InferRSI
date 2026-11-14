# Knowledge contribution workflow

This is the short path for a change to one skill in `src/inferrsi/knowledge/data/skill_library/`.
It implements the representation accepted in
[issue #355](https://github.com/InferMatrixLab/InferRSI/issues/355#issuecomment-6730172305).

## What you write and what tools derive

| You write | Tools derive |
| --- | --- |
| Skill body, references, cases, `metadata.json`, registry entry | Per-skill catalog records, resource hashes, `_provenance.json`, navigation |
| Matrix rows in `docs/reference-matrix.md` and `docs/searchspace-matrix.md` | `docs/skill-coverage.md` |
| The PR's knowledge authorship declaration: every material AI author's actual tool, model and effort, or `human_only` | The head SHA and the exact protected, policy and generated path lists |

Tooling never infers authorship, model, effort, human contribution or an exception
decision.

## Steps

1. Edit the canonical skill files and the matrices, then commit them. This commit is
   the source revision.
2. Regenerate from that commit and check:

   ```bash
   python tools/build_skill_index.py --source-revision <source-commit>
   python tools/build_skill_coverage.py
   python tools/build_skill_index.py --source-revision <source-commit> --check
   python tools/build_skill_coverage.py --check
   ```

   The recorded prefix is `src/inferrsi/knowledge/data/skill_library/`, the same
   path as the current checkout. Commit the skill and registry edits first, then
   regenerate from that commit. Do not hand-edit generated records.

3. Commit the generated changes. List the declaration paths for the final head:

   ```bash
   python tools/knowledge_declaration_paths.py --base origin/main --head HEAD
   ```
   The path lists overlap: under the current policy every generated path is also a
   protected path. Do not add their counts.

4. Write the declaration in the PR body with the reported `head_sha`. Update it after
   every new commit.

## Stored format

Stored skill records are schema 2. They keep each skill's own fields and resource
hashes. The shared `knowledge/_provenance.json` holds the full source revision and
the registry hash:

```json
{
  "schema_version": 1,
  "repository": "https://github.com/InferMatrixLab/InferRSI",
  "source_revision": "<40-hex commit>",
  "registry": {"path": "src/inferrsi/knowledge/data/skill_library/skill-index.json", "sha256": "<64-hex>"}
}
```

`registry.path` and the `source_files` keys name the library at the pinned
`source_revision`. After the explicit re-pin that path is
`src/inferrsi/knowledge/data/skill_library/`, matching the current checkout.
`skill_documents.original` and installed bundle keys stay at the package-relative
prefix `data/skill_library/`. A later move again needs an explicit new revision
that regenerates every record; do not hand-edit the generated files.

`inferrsi.catalog` resolves each stored record into a public schema-1 record with
the same fields and field order as before: the `sources` entry with the full commit
URL, and `source_files` including the registry hash. Search, `knowledge show`,
Collect and installed wheels keep reading schema 1. The generator refuses to write a
record that does not resolve back to the record it rendered.

The one-time migration regenerated all 80 records at the previous pin
`d648f25732dee1c974da62a94c46a642ad52cef8`; each resolved record was byte-identical
to the previous stored record. It then moved the pin to
`56c500367d5495fdd9f0e35030c9cd957f70eac5`, the squash commit on `main` with the
same skill-library bytes, because the previous pin is a pre-squash branch commit
and not an ancestor of `main`. Resolved records therefore differ from the previous
records only in `sources[0].commit` and `sources[0].url`; every content hash and
the registry hash are unchanged. To check the stored hashes, run
`python tools/build_skill_index.py --source-revision <source_revision> --check` with
the `source_revision` from `_provenance.json`.

## What changes per contribution

Before the shared snapshot, every skill record repeated the repository-wide source
commit and registry hash, so a one-skill edit rewrote all 80 records. Measured on
`main` at `56c50036` with one appended line in `performance-ceiling-analysis`, the
old generator changed 82 generated files (80 records, the README and the coverage
view). The new generator changes 3: that skill's record, `_provenance.json` and the
coverage view. Editing the registry or a declared status also changes the README.

Two PRs that change different skills share only `_provenance.json` and the coverage
view's input digest among generated files, so those are the expected conflicts.
Integrate the second on top of the first, keep both canonical changes, commit them
as the new source revision and regenerate; regeneration rewrites both shared files
and no unrelated record is hand-edited. Divergent edits to the same skill, or to the
same matrix row, remain ordinary content conflicts that must be resolved by hand.

## Limits

- After a squash merge, the recorded source revision is a branch commit that is not
  an ancestor of `main`. The packaged content still resolves, and `--check` still
  works when that commit is available. Git-backed SkillEval planning reports the pin
  as unavailable. This already happened with the previous format: the projections
  on `main` before this change pinned a squashed branch commit.
- Raw stored records changed from schema 1 to schema 2. Code that reads the JSON
  files directly must use `inferrsi.catalog` or `inferrsi._source_snapshot.resolve`.
- Generated files are protected knowledge paths. Regenerating them is material
  authorship work and needs a valid declaration.
