# One-command Φ-Bench A/B run

`tools/phibench_ab.py` draws a task sample, runs plain Codex (control) and
Codex + InferRSI (experiment) on every drawn task, and prints one score. It
builds on the single-task adapter in [public benchmarks](public-benchmarks.md)
and adds the batch layer: sample, isolation, retries, partial-run reporting and
score quality.

The score is the experiment arm's mean reward minus the control arm's mean
reward over tasks where both arms produced a graded reward. A positive number
means the InferRSI arm scored higher. The tool also prints wins/losses/ties,
token use, and how many scored tasks had a passing selfcheck, no host
calibration, an empty patch or a timeout.

## Prerequisites

- A local Φ-Bench clone (`tasks_index.json` at its root).
- A prepared task Python environment, or one per task through `--taskenv`.
- `proot`; the A/B run uses the `rootless` executor. Docker is not supported here because
  the InferRSI plugin arm requires the rootless executor.
- The Codex CLI and a built InferRSI Codex plugin directory.
- The model-provider variables the agent needs (`OPENAI_API_KEY`, `CODEX_HOME`,
  `HTTPS_PROXY`, ...); name them with `--agent-env`.

The tool runs the same per-task sequence as the host script: probe, three
oracle calibrations, selfcheck, control arm, then experiment arm. Calibration
replaces the suite's H20 anchor in the clone with the host median, exactly as
the suite's re-calibration procedure describes; use a clone you can edit.

## Quick start

```bash
# All 84 runnable tasks: four GPU workers and two CPU workers.
python3 tools/phibench_ab.py \
  --root phibench --out ab-20261128 \
  --plugin /path/to/inferrsi-codex-plugin \
  --venv /path/to/task-venv \
  --agent-command 'codex exec --cd /app/repo ...' \
  --agent-env OPENAI_API_KEY --agent-env CODEX_HOME \
  --gpu-prefix 'gpu run --gpus 1 --timeout 8h --note phibench --' \
  --cpu-prefix 'taskset -c 160-167'
```

Twenty tasks with the suite's type mix:

```bash
python3 tools/phibench_ab.py --n 20 --seed 1 ...same options...
```

Resume a stopped run (only unfinished tasks or failed arms with attempts left
are retried). The saved run remembers the plan and the worker options, so
`--out` is enough; passing `--n`, `--seed` or another plugin is rejected because
it would mix two plans:

```bash
python3 tools/phibench_ab.py --resume --out ab-20261128
```

Score an existing run without running anything; the saved run also remembers
the suite root:

```bash
python3 tools/phibench_ab.py --score-only --out ab-20261128
```

## Isolation and reuse

Each run owns `<out>/runs/`. A task's `summary.json` records the run id, the
plan hash (selected tasks, `--n`, `--seed`, plugin hash, agent command and CLI)
and the plugin hash. The orchestrator reuses a summary only when all three
match and the task is finished. A second `--out` with different `--n`, seed or
plugin is refused instead of silently mixing old results; `--resume` verifies
the same identity. This is the fix for the earlier failure where `--n 20
--seed 1` found 20 finished tasks and scored their old summaries without
running anything.

`--out` is required to be new, or to belong to the same run and be used with
`--resume` or `--score-only`; the tool does not overwrite an unrelated
directory. It prints how many tasks were newly run, reused and left unfinished.

## Exit status

`0` means every selected task produced a graded reward for both arms. `2` means
at least one task is unfinished, failed or unscored (the run is still written;
use `--score-only` later). `--allow-partial` makes a partial run exit `0` after
printing the missing tasks.

## Score quality

The raw mean difference is sensitive to which tasks are included. The output
therefore reports, over the selected tasks:

- selfcheck `PASS` / `FAIL` / `INCONCLUSIVE` / missing;
- tasks with no host calibration (`ref_l20` is missing);
- tasks where at least one arm captured an empty patch;
- tasks where an arm timed out;
- tasks whose probe exposed `tests/` or `solution/` to the agent (the task
  stops before the arms and is excluded from the score, not silently scored;
  start a new run after fixing the staging).

It also prints the score after excluding each of those groups, so a
small difference is not presented as a stable effect when the
inclusion rule changes its sign. The same facts are in `score.json`; per-task
rows are in `compare.json`.

## Validation on the 78-task snapshot

The 2026-11-27 snapshot (78 tasks with both arms graded) was re-scored with
this module's scoring code. It reproduces the earlier numbers: score
`-0.008486`, control mean `0.106637`, experiment mean `0.098151`. The scored
set contains `40` selfcheck `PASS`, `35` `FAIL`, `3` `INCONCLUSIVE`, `28` tasks
without host calibration and `9` with at least one empty patch. Excluding those
groups gives `+0.001614`, `-0.023792` and `-0.009593` respectively, which is why
the raw mean difference is printed next to its sensitivity rather than alone.

## Host-specific execution

- `--cli` is the command that runs the InferRSI CLI (default:
  `python -m inferrsi`). A source checkout can use
  `--cli 'python phi-cli.py' --pythonpath src`.
- `--taskenv` is a JSON object keyed by task id. Each entry may set `venv`,
  `overlay`, `replace`, `binds`, `copybinds` and `deepcopy`; these are the host
  stand-ins the rootless executor needs when a task image would build models,
  datasets or a task venv.
- `--gpu-prefix` and `--cpu-prefix` wrap each task's worker, for example a GPU
  reservation command or a `taskset` line. `{task}` and `{out}` are expanded.
- `--gpu-workers` and `--cpu-workers` set how many tasks run at once in each
  pool; both are saved with the run and restored by `--resume`.
- `--executor` is fixed to `rootless` for a run; the entry point rejects
  `docker` before starting any task instead of failing after probe/selfcheck.

## Scope

One run per task per arm, fixed arm order (control first), rootless replay when
Docker is unavailable. It does not implement the InferRSI benchmark design's
`reach(p)` or N independent repetitions; it executes the suite's tasks and
scores the two arms with the suite's grader. The suite's hidden cases are
public, so results count as a public set only.
