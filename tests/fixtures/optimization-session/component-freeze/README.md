# Harness component migration baseline

These five session archives were produced with the normal wheel from commit `3efb03ea71356786b19b705e53f65267c17d19bf`, after the runtime-closure and explicit continuation changes. They use synthetic CPU workloads. Keep the archives read-only and replay each case in a fresh directory. The [manifest](manifest.json) records the source archive, wheel and sample SHA-256 values, package version, launch receipts, commands and observed results. The [Harness interface diagram](../../../../src/inferrsi/harness/README.md#managed-session-interfaces) describes the component migration. [Frozen source](https://github.com/InferMatrixLab/InferRSI/archive/3efb03ea71356786b19b705e53f65267c17d19bf.zip) · [Migration and acceptance decisions](https://github.com/InferMatrixLab/InferRSI/issues/702)

| Frozen input | What the old installed CLI did on a copy |
| --- | --- |
| `ordinary-ab-ba.zip` | Recovered one PASS from the retained project execution. The eight original steps cover quality, warmup and two interleaved measurement pairs, in AB then BA order. Recovery started zero new processes. |
| `ordinary-packaged.zip` | Resumed after the arguments child and benchmark completed. Both `benchmarks session recover` and `campaign recover` started exactly one assessment child and committed one PASS. The original candidate ran once. A second recovery started zero processes. Only the active summary's `wall_elapsed_seconds` could change. |
| `service-pending.zip` | Settled the pending second PASS from the saved observation and recorded its existing profiling allowance once. The original deadline persisted. A second recovery left the state and stage logs byte-identical. |
| `service-settled.zip` | Reported the first PASS with zero launches and zero additional ledger entries across two recoveries. |
| `service-cleanup-pending.zip` | The candidate failed formal performance after two measurements. Quality was skipped. Recovery rejected missing or mismatched cleanup evidence with exit 2 and retained the pending round. A match settled the original FAIL once, with zero launches or measurements. |

`cleanup-proofs.zip` keeps the candidate's cleanup receipt, the real baseline attempt's receipt with its distinct service identity, and two single-field controls. One pairs the candidate attempt ID with the baseline service identity. The other replaces only the candidate attempt ID with the real baseline attempt ID, keeping the service list, PIDs and every other receipt field exactly as in the valid proof. The manifest hashes each receipt separately. Original synthetic paths, process identities and timestamps remain inside the samples because the session contract binds them. The old wheel's original executions and verification runs were on Windows.

## Reproduce the old-wheel replay

From a review checkout, build the archived revision in a clean environment. The archive includes the version information used by setuptools-scm. The commands below use a POSIX shell. On Windows, the virtual environment's Python is under `Scripts`.

```sh
checkout=$(git rev-parse --show-toplevel)
scratch=$(mktemp -d)
cd "$scratch"
python -m venv env
py="$scratch/env/bin/python"
"$py" -m pip wheel --no-deps -w wheels \
  https://github.com/InferMatrixLab/InferRSI/archive/3efb03ea71356786b19b705e53f65267c17d19bf.zip
"$py" -m pip install wheels/inferrsi-*.whl
"$py" "$checkout/tests/repository/check_harness_freeze.py" --wheel wheels/inferrsi-*.whl
```

The driver compares the 1,021 installed package files to the supplied wheel, checks every registered repository pack through its reader, and verifies the [38 frozen runtime sources](runtime-sources.json). It opens independent copies outside the checkout, observes child launches and verifies both ordinary command paths. The manifest identifies the original wheel. A rebuilt wheel may have different archive timestamps. The source, version, static fingerprint and installed payload checks still apply.

Ordinary plans pin the runtime source bytes. A later slice that changes those bytes must check both refusal on old plans and positive recovery on a matching plan. Service-reuse plans pin the package version. P8 and P9 each supply their own normal-wheel version mismatch and version match results, plus a separate same-declared-version test wheel replay against independent copies of these exact samples. Record the actual build, wheel and sample digests in each case. [Recovery acceptance matrix](https://github.com/InferMatrixLab/InferRSI/issues/702#runtime-replay)

### Reproduce the service migration checks

Build a normal wheel from the revision under review and install it in a fresh environment.
Use that environment's Python from outside the checkout to run the shared checker.
Each call verifies the installed wheel contents and extracts the archived samples into
a temporary directory.

```sh
"$py" "$checkout/tests/repository/check_harness_freeze.py" \
  --wheel "$normal_wheel" --service-replay different-version
```

For the positive control on the normal wheel, run
`test_delayed_double_recovery_settles_checkpoint_and_only_proven_time` in
`tests/apps/test_project_service_reuse.py` against the installed package. Its live CPU
service creates a checkpoint with the installed version. Missing proof, a different
attempt, and each individual identity mismatch must preserve the pending FAIL. The
matching proof settles that attempt once.

For the frozen-version control, build the same source archive in a separate directory
with `SETUPTOOLS_SCM_PRETEND_VERSION_FOR_INFERRSI` set to the manifest's
`runtime_version`. Install that wheel in a second environment and use its interpreter for the replay.

```sh
"$isolated_py" "$checkout/tests/repository/check_harness_freeze.py" \
  --wheel "$isolated_wheel" --normal-wheel "$normal_wheel" --service-replay frozen-version
```

The checker compares both wheels' package members byte for byte, allowing the generated
version module to differ, then replays all three archived service sessions. Keep this
test wheel separate from normal build artifacts.

## Source inventory and related work

The [inventory](inventory.tsv) lists all 72 tracked paths under `src/inferrsi/harness/` at the freeze, including 64 Python files, the README and seven resource packs. The importer column resolves absolute and relative Python imports. The other columns record standalone dotted names, embedded Python probes, file paths and documentation references. An entry in the reference columns can be historical documentation or a test that enforces a boundary. Split mixed modules by function, and repeat the caller search on each migration head.

Some dependencies require a symbol-level review when files move.

- P2 updates the improvement controller fingerprint in `tools/skill_eval_improve.py`. P5 replaces the work-control import of the private RunStore transaction and moves the bounded observation path and JSON helpers to Records. P6 provides the process-group cleanup check used by Manager.
- P5 and P6 update the concrete controller paths in `tools/skill_eval_compare.py` and its tests. The six `NEW_H_ENTRIES` roots and their replacements must resolve in the static graph. Moved roots join the retired import checks. Update the module-layout guide and the four contract path references with the slice that moves the symbol.
- P7 preserves per-step early stopping in ordinary projects. P8 covers inline profiling after the candidate checkpoint, interrupted capture, and standalone profile backfill. P9 updates the installed session probe's entry and action tracking. The public projection namespace `inferrsi.harness.optimization` and historical evidence paths retain their original values.

The freeze includes the continuation and runtime fingerprint changes. Concurrent work touched the ordinary and service session implementations, Apps campaign assembly and the repository-pack reader. The P1 changes add evidence and the interface diagram. Later slices should check the current file overlap, and use the D007 package-resource location at the commit being tested. [Runtime fingerprint](https://github.com/InferMatrixLab/InferRSI/pull/693) · [Final continuation](https://github.com/InferMatrixLab/InferRSI/pull/705) · [Performance-target feasibility](https://github.com/InferMatrixLab/InferRSI/pull/699) · [Task intake and project evaluation](https://github.com/InferMatrixLab/InferRSI/pull/706) · [Knowledge and Apps changes](https://github.com/InferMatrixLab/InferRSI/pull/709) · [Repository pack relocation](https://github.com/InferMatrixLab/InferRSI/pull/716)
