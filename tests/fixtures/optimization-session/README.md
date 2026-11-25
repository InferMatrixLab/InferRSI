# Optimization session fixtures

Each `*-session/` directory is a session that `main` started and interrupted with its own installed
runtime, just before a change to the runtime identity, with no edits. Its coordinator stopped after
the candidate's child finished, so each session holds a completed execution receipt for a round
that is not settled:

- `state.json` has `rounds: []` and a `pending` round, and the round directory has a completed
  `execution/execution.json` (`returncode` 0) and a `measurement/result.json`.
- `calls.log` shows that the candidate ran once.
- `plan.json` records the runtime identity of the commit that started it, including the file the
  later change removed from that identity.

| Fixture | Started by | Change | Removed identity file |
| --- | --- | --- | --- |
| `pre-infra-removal-session/` | `main` `6bdc86ee` | #498 slice 5 removed `infra/` | `infra/artifacts.py` |
| `pre-trials-rename-session/` | `75b9872`, `main` `7a7ab84` plus a docs-only commit | #558 renamed `harness/scenarios` to `harness/trials` | `harness/scenarios/external.py` |

The current runtime refuses every one of them for `status` and `recover` before any operation runs
and leaves every file unchanged. `tests/apps/test_optimization_session.py` checks this against the
checkout, and `tests/repository/check_installed.py` checks it against the installed wheel through
`INFERRSI_PRE_CHANGE_SESSIONS`, which names this directory. Neither can run the old runtime: that
needs the old commit installed in its own environment.

## Paired-wheel checks on these same sessions

Checked by hand on the H200 host (CPU only, Python 3.12). Each wheel was built from its commit's own
tree and installed in a clean virtual environment. Each session was started by the old wheel, so the
new wheel never saw it before.

| Step | `pre-infra-removal-session/` (2026-11-20) | `pre-trials-rename-session/` (2026-11-21) |
| --- | --- | --- |
| Old / new wheel | `6bdc86ee` / `c5051f8` (the merge of `6bdc86ee` into the slice-5 branch; only tests changed afterwards) | `75b9872` / `997d92d` (the rename commit; later commits change only tests and docs) |
| 1. Old wheel: `start`, `diagnose`, one `round` interrupted after the child completed | exit 0, 0, 130; `calls.log` `2`; 14 files | exit 0, 0, 130; `calls.log` `2`; 14 files |
| 2. New wheel on a copy: `status`, `recover` | both exit 2, "Optimization runtime changed, use its frozen runtime to resume"; all 14 SHA-256 values unchanged | the same |
| 3. Old wheel on the same copy: `recover`, then `status` | exit 0; `completed_rounds` 1; `calls.log` still `2` | the same |

Step 3 shows that recovery used the receipt and did not run the candidate again.

To redo it for a later runtime change: build and install the old and the new wheel in separate
environments, start the session with the old one (the synthetic task of
`tests/apps/test_optimization_session.py`, `--rounds 3 --max-minutes 5 --evaluation-timeout-seconds 15
--python python`, run from a neutral directory so no host path enters the plan), stop its coordinator
after the child completes, remove the empty `.session.lock`, and keep everything else. Add the new
directory and its removed identity file to both tests.

To resume such a session, use the runtime that started it: the same commit, installed.

`.gitattributes` marks each session directory `-text` because `plan.json` pins file hashes, and
`pyproject.toml` excludes them from ruff for the same reason.

`pre-serving-runtime-identity.json` holds the runtime identity of `main` at `25df477`, from before
#498 slice 2. It is used by a test that swaps it into a freshly started session.
