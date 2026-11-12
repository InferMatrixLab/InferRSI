# Apps output review validation

This is a development-test transcript summary, not design acceptance, a full-suite
success claim, or a production/crash-durability certification. The corresponding
PR reply identifies the candidate commit. Commands ran on 2026-11-12.

## Focused regression command

```text
python -m pytest tests/test_apps_output.py tests/test_apps_port_validation.py tests/test_apps_publication.py tests/test_apps_replay.py tests/test_harness_run_store.py tests/test_target_module_import_gate.py tests/test_smoke.py -ra
```

Windows, CPython 3.12, local NTFS:

```text
127 passed in 11.20s
ruff check src tests tools
All checks passed!
git diff --check
(no output; exit 0)
```

Linux, Ubuntu 24.04 in WSL, CPython 3.12, temporary output/store directories
on native Linux /tmp (source checkout on drvfs):

```text
127 passed in 76.97s (0:01:16)
```

For that Linux run an isolated temporary venv referenced the existing pure-Python
pytest installation through a .pth file, with PYTEST_DISABLE_PLUGIN_AUTOLOAD=1.
Official-package-source installation was attempted first but failed because DNS
in WSL and the configured Windows proxy were unavailable. No network settings
were changed. An earlier system-Python run had 126 passes and one subprocess
failure because its reset PYTHONPATH omitted pytest; the venv run above includes
that same subprocess replay test and passes. This is not a standard freshly
installed Linux dependency environment.

## Full-suite limits

Windows `python -m pytest -x --tb=line -rN` stopped with:

```text
45 passed, 2 errors in 2.83s
ValueError: the environment variable is longer than 32767 characters
```

Setup and teardown of the existing, unmodified
`test_hostile_http_body_is_rejected_without_leakage` large-response parameter
hit the Windows environment-variable limit through its huge pytest node ID.
The platform exception was independently reproduced without importing project
code by assigning a 40,000-character string to an environment variable. No test
was disabled or shortened to obtain a full-suite green result. A preceding full
run was interrupted without a final summary. Neither run is a full-suite pass.
This does not establish the cause of the historical WSL full-suite exit 1.

## What these checks cover and do not cover

The focused set exercises malformed replies and foreign error identities, a
real H RunStore held by a separate process, digest conflict, owner-gone recovery,
commit-preserving replay, import boundaries, and local no-replace publication.
The H integration tests use fixed terminal payloads and injected ports, not a
production engine or model service. Directory-fsync ordering and failure paths
also use deterministic fault injection; no power-loss experiment was performed.
macOS, NFS, FUSE, drvfs output publication and remote filesystems were not tested.
See [publication contract and limits](apps-output.md).
