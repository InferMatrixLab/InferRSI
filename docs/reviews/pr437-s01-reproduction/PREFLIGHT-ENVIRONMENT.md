# Qualify preflight environment (why two Linux/bwrap hosts can disagree)

`inferrsi.harness.artifact_sandbox.replay()` runs a **probe** invocation inside
`bwrap --unshare-all …` before any control. If the probe does not return
`{"ready": True}`, it raises `SandboxUnavailable("Artifact sandbox preflight
failed; no host fallback")` and does **not** fall back to the host. Qualification
then reports INCONCLUSIVE with empty controls. That is the designed failure
mode, not a PASS/FAIL on the parser controls.

The PASS receipt in `receipts/qualify-8b4a0cf-debian13/` was produced on:

- Linux 6.12.113+ x86_64, Debian GNU/Linux 13.7 (trixie), glibc 2.41
- `/usr/bin/python3` = CPython 3.13.5
- bubblewrap 0.12.0
- User namespaces already enabled; **no** `sysctl`, AppArmor policy, or
  service change was made for that run
- Runner-image *label* `debian-13.7/local-box-bwrap-0.12.0` (this is a label,
  not the GitHub `ubuntu-22.04` workflow image)

A later review run at the same git tree, on Linux / Python 3.12.14 /
bubblewrap 0.12.0, reported the preflight failure and empty controls. The
tree is the same; the **host sandbox capability** is not. Common causes of
that exact error, given that `bwrap` itself is installed:

1. Unprivileged user namespaces are disabled or exhausted
   (`/proc/sys/kernel/unprivileged_userns_clone` is `0`, or
   `/proc/sys/user/max_user_namespaces` is `0`), or the process is already
   inside a container/user namespace that cannot nest `--unshare-all`.
2. `/usr/bin/python3` is missing, is not a `python3.X` CPython, or the
   corresponding `/usr/lib/python3.X` stdlib (and a lib64/multiarch lib dir)
   is not present. The sandbox binds **system** Python only; a conda/venv
   or `/usr/local` interpreter used to *launch* qualify does not get mounted
   inside bwrap. Python 3.12 vs 3.13 is fine if `/usr/bin/python3` and its
   stdlib resolve; it is not fine if launch Python is 3.12 from a prefix
   that is not the system layout the sandbox expects.
3. LSM / userns restrictions (AppArmor, Debian `kernel.apparmor_restrict_unprivileged_userns`,
   etc.) that allow `bwrap` to exist but cause `--unshare-all` or the probe
   process to fail.

Diagnostic (no sysctl change required to *run the diagnosis*):

```bash
python3 docs/reviews/pr437-s01-reproduction/reproduce.py preflight-diag
# or, manually:
bwrap --version
ls -l /usr/bin/python3; /usr/bin/python3 --version
cat /proc/sys/kernel/unprivileged_userns_clone
cat /proc/sys/user/max_user_namespaces
bwrap --unshare-all -- /bin/true; echo exit=$?
```

This pack does **not** recommend weakening the sandbox or enabling host
fallback. If preflight fails on a reviewer host, treat that run as
INCONCLUSIVE and compare the facts above to the attached PASS receipt
rather than treating the two results as a content disagreement on
`8b4a0cf` / `03a6a62`.
