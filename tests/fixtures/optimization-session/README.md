# Optimization session fixtures

`pre-infra-removal-session/` is a session that `main` `6bdc86ee` started with its own installed
runtime, with no edits. Its `plan.json` records the runtime identity of that commit, which
includes `infra/artifacts.py`. The runtime of #498 slice 5 no longer hashes that file, so it
refuses this session for `status` and `recover` before any operation runs and leaves every file
unchanged. `tests/test_optimization_session.py` checks this against the checkout, and
`tests/check_installed.py` checks it against the installed wheel.

How it was made, so it can be redone for a later runtime change:

1. Build a wheel of the old commit and install it in a clean virtual environment.
2. Run `benchmarks session start` with the synthetic task of `tests/test_optimization_session.py`
   (`--rounds 3 --max-minutes 5 --evaluation-timeout-seconds 15 --python python`) from that
   environment, so no host path enters the plan.
3. Remove `.session.lock`, which is an empty lock file, and keep everything else.

To resume such a session, use the runtime that started it: the same commit, installed.

`.gitattributes` marks the directory `-text` because `plan.json` pins file hashes.

`pre-serving-runtime-identity.json` holds the runtime identity of `main` at `25df477`, from before
#498 slice 2. It is used by a test that swaps it into a freshly started session.
