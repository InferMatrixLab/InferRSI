# Engineering task artifacts in SkillEval

`engineering-benchmark-v1` connects the packaged `softmax-cpu` task to
`tools.skill_eval_compare` in **update mode**. It freezes two skill versions,
retains each producer's actual `implementation.py`, and grades correctness with
the shared task oracle. It does not measure speed. Reviewed implementations can
later enter a separate [Workbench comparison](engineering-benchmarks.md).

## Prepare the task and comparison

Run from a development checkout. Generate a canonical case rather than editing
its contract or relying on a same-named directory in the working tree:

```bash
python -c "from inferrsi.harness.skill_eval_benchmark import task_descriptor; from inferrsi.infra.artifacts import write_json; from pathlib import Path; write_json(Path('cases.json'), [task_descriptor('softmax-cpu')])"
```

Create `config.json` beside `cases.json`:

```json
{
  "adapter": "engineering-benchmark-v1",
  "mode": "update",
  "skill": "<skill-id>",
  "skill_root": "<repo-relative-skill-root>",
  "cases": "cases.json",
  "snapshots": {
    "baseline": {"git_revision": "<old-skill-full-commit>"},
    "candidate": {"git_revision": "<new-skill-full-commit>"}
  },
  "model": {"name": "<approved-model>", "effort": "<frozen-effort>"},
  "limits": {
    "repeats": 1,
    "max_task_calls": 2,
    "timeout_seconds": 60,
    "campaign_seconds": 180,
    "token_stop_new_trials": 10000
  }
}
```

The example limits are illustrative; choose and freeze the actual bounds before
execution. Use full commits available in the local repository. Do not add a
provider client, custom schema or grader. See [comparison configuration](skill-eval-comparison.md)
for Git prerequisites, snapshot rules and budget semantics.

```bash
python -m tools.skill_eval_compare prepare --config config.json --repo <skill-checkout> --output <new-evidence-directory>
```

Preparation freezes task, starter, schema, verifier/controllers and skill
bundles. Formal loading always uses canonical packaged resources. Retained task
copies must match that descriptor. The supplied CPU starter is already correct;
leaving it unchanged can pass, so correctness alone cannot identify optimization.

## Hand off and retain actual files

Stage a fresh workspace outside the evidence tree for one arm:

```bash
python -m tools.skill_eval_compare execute --output <evidence-directory> --authorize <plan-sha256> --stage-local <new-baseline-workspace> --task-id softmax-cpu --condition baseline --repeat 1 --current-head <new-skill-full-commit>
```

Stage does not launch an Agent. Run the producer under the caller's established
permissions and budget. Only `implementation.py` may change; keep task,
instructions and assigned knowledge frozen. The file implements
`compute(x, *, eps)` with self-contained NumPy/math helpers. Its final answer is:

```json
{"artifact": "implementation.py", "summary": "Describe the actual change"}
```

Stop the producer before capture. Retain `stdout.log`, `stderr.log` and
`execution.json` in a separate submission directory, following the exact fields
in [author-run handoff](local-skill-evaluation.md#author-run-handoff).
Model, access, resources and usage in these files are author-reported, not
authenticated observations. Missing usage stays unknown.

```bash
python -m tools.skill_eval_compare execute --output <evidence-directory> --authorize <plan-sha256> --capture-local <baseline-workspace> --submission <baseline-logs> --task-id softmax-cpu --condition baseline --repeat 1 --current-head <new-skill-full-commit>
```

Repeat stage/produce/capture for `--condition candidate` with distinct workspace
and log directories, then run:

```bash
python -m tools.skill_eval_compare report --output <evidence-directory>
```

The plan hash binds this attempt; it does not authorize model spending. Changed
inputs require a new plan. Capture preserves actual source bytes and hashes;
report rechecks retained artifacts without rerunning the producer. Failed or
incomplete attempts remain recorded and cannot be overwritten as clean results.

## Execution boundary and interpretation

The trusted parent owns inputs, the scalar oracle and assertions. Submitted
source executes in a Linux bubblewrap child with system Python, matching NumPy
and a bounded runner; the repository, grader and other arm are not mounted.
Every returned array is checked by the parent. The public suite does not prove
hidden-test generalization, hostile-protocol resistance or independent tracing
of every candidate operation. Producer permissions are a separate boundary.

Windows, missing bubblewrap/namespace support or an incompatible NumPy runtime
produce `artifact_sandbox_unavailable` / INCONCLUSIVE without host fallback.
NPU tasks are explicitly rejected. CPU replay qualification does not establish
NPU isolation, and the default unrestricted Agent client is refused for automatic
engineering runs. Provider generation and the offline improvement controller do
not support this adapter.

A PASS means correctness on the public input sequence, not faster code. A local
handoff report showing `artifact_improved` establishes a difference in retained
artifact checks, not a causal skill benefit or verified total cost. Performance,
Agent efficacy and service claims need their own controlled evidence. Profiling
is optional and is not invoked by this adapter.
