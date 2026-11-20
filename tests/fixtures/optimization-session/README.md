# Optimization session fixtures

`pre-infra-removal-session/` is a session that `main` `6bdc86ee` started and interrupted with its own
installed runtime, with no edits. Its coordinator stopped after the candidate's child finished, so
the session holds a completed execution receipt for a round that is not settled:

- `state.json` has `rounds: []` and a `pending` round, and the round directory has a completed
  `execution/execution.json` (`returncode` 0) and a `measurement/result.json`.
- `calls.log` shows that the candidate ran once.
- `plan.json` records the runtime identity of that commit, which includes `infra/artifacts.py`.

The runtime of #498 slice 5 no longer hashes that file, so it refuses this session for `status` and
`recover` before any operation runs and leaves every file unchanged. `tests/test_optimization_session.py`
checks this against the checkout, and `tests/check_installed.py` checks it against the installed
wheel. Neither can run the old runtime: that needs the old commit installed in its own environment.

## Paired-wheel check on this same session

Checked by hand on the H200 host on 2026-11-20 (CPU only, Python 3.12). Old wheel = `main`
`6bdc86ee`, new wheel = the merge of `main` `6bdc86ee` into the slice-5 branch (`c5051f8`; only tests
changed afterwards). Each wheel was built from its commit's own tree and installed in a clean virtual
environment. The session below was started by the old wheel, so the new wheel never saw it before.

1. The old wheel ran `benchmarks session start`, `diagnose` and one `round` that was interrupted after
   the child completed (exit 130). `calls.log` was `2`. Its 14 files are this directory.
2. On a copy, the new wheel exited 2 for `status` and for `recover` with "Optimization runtime
   changed, use its frozen runtime to resume", and the SHA-256 of all 14 files was the same after.
3. On the same copy, the old wheel exited 0 for `recover`. `status` then reported `completed_rounds` 1,
   and `calls.log` was still `2`, so recovery used the receipt and did not run the candidate again.

To redo it for a later runtime change: build and install the old and the new wheel in separate
environments, start the session with the old one (the synthetic task of
`tests/test_optimization_session.py`, `--rounds 3 --max-minutes 5 --evaluation-timeout-seconds 15
--python python`, run from a neutral directory so no host path enters the plan), stop its coordinator
after the child completes, remove the empty `.session.lock`, and keep everything else.

To resume such a session, use the runtime that started it: the same commit, installed.

`.gitattributes` marks the directory `-text` because `plan.json` pins file hashes, and `pyproject.toml`
excludes it from ruff for the same reason.

`pre-serving-runtime-identity.json` holds the runtime identity of `main` at `25df477`, from before
#498 slice 2. It is used by a test that swaps it into a freshly started session.
