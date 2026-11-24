# Knowledge contribution workflow

This is the short path for a change to one skill in `src/inferrsi/knowledge/data/skill_library/`.
It builds on the earlier projection format discussed in
[issue #355](https://github.com/InferMatrixLab/InferRSI/issues/355#issuecomment-6730172305).

## What you write and what tools derive

| You write | Tools derive |
| --- | --- |
| Skill document (including frontmatter), references, cases, registry entry | Runtime catalog views, compiled YAML headers and resource hashes |
| Matrix rows in `docs/reference-matrix.md` and `docs/searchspace-matrix.md` | `docs/skill-coverage.md` |
| The PR's knowledge authorship declaration: every material AI author's actual tool, model and effort, or `human_only` | The head SHA and the exact protected, policy and generated path lists |

Tooling never infers authorship, model, effort, human contribution or an exception
decision.

A skill owner edits one `SKILL.md`. Put structured InferRSI fields in the
`metadata.inferrsi` literal string. The host sees a string-valued annotation,
and InferRSI reads its JSON object. For example, a candidate owner can declare:

```yaml
---
name: example-skill
description: "Inspect an inference configuration."
metadata:
  inferrsi: |
    {"status": "candidate", "tags": ["configuration"]}
---
```

Write the procedure after the closing delimiter. Add references or cases only
when the procedure needs those resources.

### Decision fields and Case finding identity

Review decision fields in the canonical source. For a Skill use the
`metadata.inferrsi` object above. For a Record use its authored JSON. Put the
conditions for use in `applicability`, with `prerequisites` or `conditions`
when available. Preserve explicit `refusal_point`, `failure_modes` and
`limitations`. Use `recommendations` for the proposed action and
`validation_plan` for the checks. Keep imported claims, measurements and
verification in the source's own vocabulary. An absent field is visible on a
partial card, so authors can review gaps without inventing a conclusion.

For a new finding in a Case's `findings` array, choose a stable, unique string
`id` within that Case and retain it when editing or reordering the finding.
Keep its attempted `direction`, `outcome` and `reason` together. Record
`scope`, `bounds` and `revisit_when` when the evidence supplies them.
Existing entries without a unique ID use a position in the revision-pinned
original JSON. For example, the historical Sarathi TTFT/TBT comparison is
`case.sarathi-chunk-budget` at `case.json#/findings/3` in the source revision
returned by Find. Reviewers can compare its card and original using the
[decision card read contract](knowledge-operations.md#read-a-decision-card).

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
   regenerate from that commit. The generator writes both files under `skill_library/_compiled/`.

3. Commit the generated changes. List the declaration paths for the final head:

   ```bash
   python tools/knowledge_declaration_paths.py --base origin/main --head HEAD
   ```
   The path lists overlap: under the current policy every generated path is also a
   protected path. Do not add their counts.

4. Write the declaration in the PR body with the reported `head_sha`. Update it after
   every new commit.

## Packaged format

The only authored engineering records are `skill_library/records/<id>.json`. Their source tier, provenance and validation state travel with the record. For registered skills the catalog assembles the public schema-1 view from the registry, the canonical metadata and two generated inputs. `_compiled/inputs.json` stores each owner's original YAML header and Git file hashes keyed by its local resource names. `_compiled/_provenance.json` stores the source revision and registry hash. The body remains in SKILL.md. The base wheel can reconstruct views without Git or PyYAML. Indexed material selection checks actual resource hashes against the declaration.

A concurrent edit to two owners can conflict in the compiled files. Resolve the canonical edits first, commit their combined sources and regenerate. The deterministic checker compares the generated files with their committed contents. Old raw projection paths were removed. Consumers can look up the same stable ID with `knowledge show`.

After a squash merge, the recorded source revision can fall outside the new main branch history. The installed wheel still contains its inputs. Git-backed SkillEval planning requires a reachable source pin and reports an unavailable check otherwise.
