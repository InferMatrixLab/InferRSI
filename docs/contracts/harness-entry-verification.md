# Harness source-entry verification

The local CPU target can opt into the first frozen evaluation task with
`LocalCpuTarget(..., module_root=<trusted absolute directory>)` from
`inferrsi.harness.executor`. The host owns
this configuration. Requests cannot supply the root. Existing targets with no
module root retain their ordinary-command behavior and refuse evaluation mode
before registration.

The first target supports a standalone source entry named
`module_root/<entrypoint>.py` with `entrypoint_kind="python_module"`. It reads a
regular file inside that root, without importing worker code or package
initializers. Dotted packages, bytecode/native modules and native executables
remain unsupported on this evaluation target. No ambient module/path fallback
is attempted. Ordinary-command module/executable resolution is unchanged.

## Ordering and retained facts

1. Static shape and fixed-preparation declaration checks run before registration.
   Malformed bindings still produce no attempt or record.
2. RunStore registers the request and ordinary admission runs.
3. Harness copies the actual entry into its private attempt capture directory,
   independently checks the retained bytes, and compares their SHA-256 with the
   expected digest already bound to the frozen preparation.
4. A mismatch yields a fixed `not_started` record. Its
   `entry_code_identity` check is `failed`, the runtime binding contains the
   observed actual digest, and the check references the retained source bytes.
5. An unavailable/unsupported entry yields a fixed `not_started` record with a
   `not_performed` check and no source reference. A source-module binding keeps
   the actual digest null and the unresolved argv empty. No mismatch is invented.
6. A matching standalone module executes from its captured source file using the
   current Python interpreter with `-I -B`. The workspace and `PYTHONPATH` cannot
   replace the bound entry, and subsequent changes to its original source file
   do not change the bytes being executed. Package execution is outside this
   target's supported range. The runtime binding records the resolved command.

Runtime bindings describe resolution, not proof of a process launch. On an N1
mismatch, `argv` is the would-be command over the captured source and the step
remains `not_started`; `started` and step facts determine whether anything ran.
On N2 it is empty because the source command could not be resolved. This target
intentionally binds the frozen recipe's single worker step; declaration checks
reject multiple steps, so each private entry directory holds one snapshot.

Both refusal cases launch zero worker processes, acquire no process lease, and
retain the preparation/protocol/candidate identity in the fixed record. The
source proof uses `python-source@1`; its SHA is the observed byte identity, not
the frozen expectation copied into an observation. The complete interpreter is
not archived. Re-reading the fixed revision preserves those facts.

The entry capture is a Harness write. A capture failure uses the existing
`ExecutionPersistenceError` path with `started=false`. Record commit failure
also preserves that known start state and cannot produce a committed RecordRef.
There is no process fallback after an entry failure.

## Delivery boundary

These checks implement the post-registration T37-N1/N2 boundary separately from
the pre-registration binding tests. A real matching source entry is a positive
control. CPU execution facts and exit zero are not a Benchmark verdict.

The production preparation/Apps archive cross-tests use the accepted D023 /
`t108-v4` family and actual source bytes. Their small software worker does not
claim complete F/C/M evidence, a service gain, or whole-Issue production
acceptance. Existing ordinary CPU supervision is reused. The
[original-limit/T40 contract](harness-evaluation-replay.md) describes the next
unit; complete CPU acceptance retains its separate launch-boundary prerequisite.
