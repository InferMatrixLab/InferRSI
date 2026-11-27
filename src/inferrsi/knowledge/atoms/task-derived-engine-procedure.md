## Run the procedure

1. Pin the parent repository, revision, build and known-good run. Identify inherited modules and the fork-owned seam. State what API, model behavior and state ownership must be preserved and what observable behavior should change.
2. Run the actual model, script and flags on the parent. Capture outputs, state transitions and benchmark results. Build the smallest fork slice at the chosen seam on the same target.
3. Run a matched inherited-path check with the extension disabled or bypassed where supported. Run a separate case that exercises the intended delta. At the first mismatch, replay the same input at the parent/fork boundary before extending the change.
4. Repeat end to end with the user's flags and acceptance workload. Report inherited-path regressions, delta behavior, and performance or memory trade-offs separately.

