# Public benchmark suites

InferRSI can run tasks from a public benchmark suite and score them with that
suite's own grader. The first suite is
[Φ-Bench](https://github.com/one2piece2hello/faibench_Frontier_InfraBench)
(arXiv:2609.10226, Apache-2.0): 85 LLM-infrastructure tasks, each a Docker build
context with a starting tree, a grader under `tests/` and reference landings
under `solution/`.

The adapter keeps four steps separate, so a later suite only needs a new task
reader:

1. **Task package**: read the suite index and one task package.
2. **Change**: land a reference control, a candidate patch or one agent command
   in the task's working tree.
3. **Patch**: capture the working-tree diff with the package's
   `pre_artifacts.sh`.
4. **Independent grading**: run the package's `tests/test.sh` and read the
   `reward.json` it writes.

Benchmark owns steps 1 and 4 (`inferrsi.benchmark.external.phibench`); Apps
owns execution (`inferrsi.apps.workflows.external_benchmark`). InferRSI does not
vendor any task, grader or reference solution. Clone the suite yourself.

## Commands

```bash
git clone https://github.com/one2piece2hello/faibench_Frontier_InfraBench phibench
inferrsi benchmarks external list --root phibench
inferrsi benchmarks external selfcheck --root phibench --task kfc/<name> \
  --executor docker --oracle-tolerance <frozen-tolerance> --output runs/<name>
inferrsi benchmarks external run --root phibench --task kfc/<name> \
  --executor rootless --proot /path/to/proot --mode candidate \
  --candidate-patch candidate.patch --output runs/<name>-candidate
```

`run --mode` takes `noop`, `negative`, `oracle`, `candidate` (with
`--candidate-patch`) or `agent` (with `--agent-command`, a shell command run in
`/app/repo` with `PHI_INSTRUCTION=/app/instruction.md`). Each mode writes
`<output>/<mode>/result.json` with the landing, capture and grading logs, the
captured patch size and the grader's score. `selfcheck` runs the three controls
and writes `<output>/selfcheck.json`; it exits 0 only on `PASS`.

Agent mode follows the suite's split: `tests/` and `solution/` are **not** in
the agent's step (the suite mounts them only for grading), so an agent cannot read
the hidden cases or the reference patch. proot otherwise shares the host
filesystem, so the rootless executor also covers the suite clone with an empty
directory for the agent step; keep `--python-env`, other copies of the suite and
earlier control runs (they stage `solution/`) outside it or out of reach. The
grading step starts from a fresh `tests/` and an empty `/logs/verifier`. An agent
that exits non-zero or hits its timeout is still graded on the tree it left, as
the suite runner does; `result.json` lists it under `warnings`. A grader cut off
at its own timeout adds the hard fail `verifier_timed_out`; that run has status
`verifier_timeout` and `run` exits 1, even when the grader left a reward behind
(the raw score stays in `result.json` for audit), and a control whose grader timed
out is `INCONCLUSIVE`. A grader that leaves no readable reward (`reward.json`, `metrics.json` or `reward.txt`) adds `no_reward_file`; that run has status `no_reward` and `run` exits 1. A grader that exits 124 or 137 counts as timed out too. `task.toml` is read with the same TOML parser as the suite runner, so comments, digit separators and exponents mean the same thing. Without a `timeout_sec` in `task.toml` the steps use the suite runner's defaults (agent 5400 s, grader 3600 s); a reference landing (`oracle`, `negative`, `noop`) is capped at 1800 s, as in the suite runner. `--agent-env NAME` forwards an
environment variable by name into the agent step only (model-provider keys,
`HTTPS_PROXY`, `CODEX_HOME`). The value goes into a mode-600 file inside the
task root (removed after that step), not into the result or the host process
table; the grading step does not inherit it. The agent step is bounded by the
task's own `[agent] timeout_sec` in `task.toml`.

`--inferrsi-plugin DIR` (agent mode, rootless executor) runs the same agent with
InferRSI, using the [Codex plugin](../guides/plugins/codex-plugin.md) the
standard way for a client that cannot import the plugin archive: the built
plugin directory (`tools/build_codex_plugin.py`, or the unpacked Release ZIP) is
placed at `/opt/inferrsi-plugin`, and a short note appended to
`/app/instruction.md` tells the agent to use InferRSI through that directory's
`SKILL.md` and launcher. Choosing skills and searching knowledge stay with the
agent; nothing is retrieved for it in advance. The original instruction is
restored before grading, `tests/` and `solution/` stay out of the agent's step,
and `result.json` records the plugin's version and `content_sha256` under
`inferrsi`. The task image's interpreter runs the launcher; operations that parse
skill frontmatter need PyYAML there. Without the flag the run is unchanged, so it
is the plain-agent control: keep the task, model, effort, timeout and run count
identical between the two arms.

## Executors

- `docker` delegates to the suite's `scripts/run_task.py`, which builds the
  task image and grades in a fresh offline container. This is the suite's
  reference path. In this slice it runs the reference controls; pass extra
  runner options with `--runner-arg`.
- `rootless` is for hosts without Docker or user namespaces. It recreates the
  image layout in the output directory and maps it onto `/app`, `/opt`,
  `/tests` and `/logs` with [proot](https://proot-me.github.io/). It replays the
  Dockerfile's `COPY`, `ARG` defaults and `ENV`, the one-commit baseline of
  `/app/repo` and the frozen `/opt/verifier-baseline` copies. It does not run
  other `RUN` steps or the image entrypoint (its `/app/timer.sh` budget stub).
  Provide a Python environment with the task's dependencies through
  `--python-env`; otherwise it creates an empty venv, which is enough
  for standard-library tasks. Every result records `fidelity: approximate` and
  lists the Dockerfile steps it did not replay. proot does not enforce the
  read-only `tests/` mount or the offline network that Docker grading uses.

## Control expectations

The self-check follows the suite's own documentation (README "Important
Conventions", `SCORING.md`):

| Control | Landing | Expected |
| --- | --- | --- |
| `noop` | starting tree unchanged | reward 0 |
| `negative` | known-bad `negative.patch` | reward 0 |
| `oracle` | reference `oracle.patch` | implementation task: reward 1.0; performance task: no hard gate, measured speedup equals `ref_speedup` within `--oracle-tolerance` |

Performance tasks use the curve `reward_md_log_speedup_v2_oracle_zero`, which
gives 0 to a submission that ties the anchor. A correct oracle therefore scores
0, and the self-check judges it on its hard gates and measured speedup instead.
Without `--oracle-tolerance` a performance oracle is `INCONCLUSIVE`. Anchors were
calibrated on an NVIDIA H20 or the authors' CPU lane; on other hardware a timed
oracle can miss the anchor and the task needs re-calibration before scoring.

## Re-calibrating a timed task on a new host

The grader reads the anchor from the task package's `tests/ref_speedup.txt`
first (`task.toml` `ref_speedup_source`), so a re-calibration is host-local: it
never changes InferRSI. Run the reference landing at least three times on a
quiet GPU, take the median, and write it back into the package:

```bash
for i in 1 2 3; do
  inferrsi benchmarks external run --root phibench --task kfc/<name> \
    --executor rootless --proot proot --python-env <task-venv> \
    --mode oracle --output runs/cal-$i
done
# median of runs/cal-*/oracle/result.json -> score.speedup
printf '5.4874\n' > phibench/tasks/kfc/<name>/task/tests/ref_speedup.txt
inferrsi benchmarks external selfcheck ... --oracle-tolerance 0.03
```

On one NVIDIA L20X (torch 2.7.0+cu126, triton 3.3.0) the H20 anchor 6.4424 for
`kfc/merge-attn-states-combine` measured 5.5196 / 5.4874 / 5.4720 over three
fresh oracle runs (median 5.4874, 0.9% spread); the corresponding self-check
passed with the new anchor at a 3% tolerance (about twice the observed
half-spread). Re-measure per host and per run stack; do not copy these numbers
to another machine.

## Scope of this slice

This entry checks that a suite task, its controls and its grader work on a
host, including one real agent run on a GPU task. It does not yet score InferRSI
against the suite. Scoring under the
[InferRSI benchmark design](https://github.com/InferMatrixLab/InferRSI/issues/665)
(fixed budget, N independent runs, `reach(p)`) is a later slice; the anchor
procedure above calibrates one task on one host, not the whole suite. Φ-Bench's
hidden cases are public, so its results count as a public set only.
