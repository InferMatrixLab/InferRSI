# Knowledge contribution workflow

This is the short path for a change to one skill in `src/inferrsi/knowledge/data/skill_library/`.
It builds on the earlier projection format discussed in
[issue #355](https://github.com/InferMatrixLab/InferRSI/issues/355#issuecomment-6730172305).

## Review a changed Skill with Find and Read

Run this Python example with the `inferrsi` CLI on your path. It keeps two
temporary copies of one authored file, `align-traces/SKILL.md`. The query
matches the Skill's `description` at L0. At L1 the reviewer can inspect
what to do, when to stop and how to check the result.

```python
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory


def cli(*args):
    return json.loads(subprocess.check_output(["inferrsi", *args]))


fields = {
    "empirical_validation": "not_run",
    "applicability": {
        "scope": "Two traces of the same request set.",
        "prerequisites": ["Each trace records a request ID per row."],
        "refusal_point": "Stop if any row has an empty or repeated ID.",
    },
}
pins = []
with TemporaryDirectory() as tmp:
    for version in ("before", "after"):
        root = Path(tmp, version)
        owner = root / "align-traces"
        owner.mkdir(parents=True)
        if version == "after":
            fields["recommendations"] = ["Join trace rows by request ID."]
            fields["validation_plan"] = [
                "Compare the two ID sets. Expect an empty symmetric difference."
            ]
        header = "---\nname: align-traces\ndescription: Check request alignment in saved traces.\n"
        (owner / "SKILL.md").write_bytes(
            (header + "metadata:\n  inferrsi: |\n    " + json.dumps(fields)
             + "\n---\nUse the saved reference and candidate traces.\n").encode("utf-8")
        )
        query = ["find", "request alignment", "--skill-root", str(root), "--kinds", "skill",
                 "--no-external", "--json"]
        hit, = cli(*query, "--decision-cards")["items"]
        pin = hit.pop("decision_card")
        assert [hit] == cli(*query)["items"]  # The default hit still opens the body.
        pins.append(pin)
        card = cli(*pin["read_args"])["card"]
        assert card["revision"] == pin["revision"]
        print(version, card["revision"])
        print(card["status"], card["missing_fields"], card["declared"]["empirical_validation"])

    assert pins[0]["ref"] == pins[1]["ref"] and pins[0]["revision"] != pins[1]["revision"]
    assert cli(*pins[0]["read_args"])["card"]["status"] == "partial"
    print(*card["decision"]["recommendation"])
    print(card["decision"]["refusal_or_limits"]["refusal_point"])
    print(*card["decision"]["validation"])
```

The first read reports `partial ['recommendation', 'validation'] not_run`.
The second reports `complete [] not_run` and prints the action, refusal point
and proposed check. The expected observation is still a plan. Keep unknown
fields absent when reviewing a real change.

For a Record, open its hit's `decision_card.read_args`. Compare the decision
and original `verification` with the authored JSON using `next_read_args`.
For a Case, open the selected **finding's** `decision_card.read_args`. Follow
`source_read_args` to review its direction, outcome, reason, bounds and
revisit condition in the original `case.json`. A positional pointer identifies
that finding only in that revision. Run Find again after an edit. Correct the
canonical source and regenerate derived files using the steps below.

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
