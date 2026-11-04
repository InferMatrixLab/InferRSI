# Fixed synthetic CPU workbench

Read task.json, CONTRACT.md, candidate.py and development.json. Only candidate.py
may change. The exposed development file contains public case IDs and events;
trusted expected outputs remain outside the read allowlist.

Use write_candidate to retain a revision, run_visible_checks for bounded public
correctness feedback, and run_visible_benchmark for fixed whole-command AB/BA
timing against the starter. Measurement includes sandbox/interpreter startup and
requires correct complete output. Rewriting invalidates previous receipts.
Submit only after checks and measurement on the current revision. Hidden final
grading occurs after immutable submission and never feeds another edit.

This synthetic feasibility task does not establish production performance or
knowledge efficacy. Any knowledge files explicitly exposed in the manifest are
fallible guidance; their outbound links do not expand the read allowlist.
