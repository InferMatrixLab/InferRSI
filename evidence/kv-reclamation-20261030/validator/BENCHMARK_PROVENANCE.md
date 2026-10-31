# Supplemental synthetic benchmark output oracle, version 1

This separate freeze supplements, and does not rewrite, the original independent
contract verifier whose `FREEZE.json` SHA-256 is
`163c21134a8155da2a6469d9dbddb6ea71cb162e14f53e1c4266fe8ce75126f7`.
No original contract, trace, expected observation, or frozen file was changed.

The independent verifier author inspected only the protected workload source
after the original freeze. `source_workload.py` is an unchanged copy of that
input generator, preserved here to identify and test this narrowly applicable
closed-form oracle. Candidate, optimized control, target knowledge, and model
outputs were not inspected to derive these benchmark expectations. The module
imports none of them. No model/provider/GPU calls or external writes occurred.

## Derivation

For positive integer count N, the pinned input contains N allocations, N finishes
in reverse order, N save completions in forward order, then frontiers 0 through
256. Allocation i has blocks `[2i, 2i+1]`, write step i modulo 257, and save
required unless i is divisible by 3.

1. The processed frontier remains -1 during the first 3N events. Every write step
   is nonnegative, so the fence predicate is false and every output is empty.
2. Before the first frontier advance, every allocation is finished and has its
   own matching save completion. Thus every finish/save predicate is satisfied,
   including allocations for which saves are optional.
3. Frontier f is visited in ascending integer order. Exactly the unreclaimed
   indices i with i modulo 257 = f become newly eligible. The output concatenates
   their two blocks in ascending i order, as required by allocation ordering.
4. Every write step lies in [0, 256], so the final queue is empty and each block
   appears exactly once in the output partition.

`benchmark_expected(count)` returns
`{"observations": [{"reclaimed": [...]}, ...], "pending": []}`. It intentionally
omits intermediate pending snapshots to avoid quadratic observation volume.
This is only the protected benchmark's output oracle; complete event-wise state,
invalid input handling, lifecycle identity/reuse and all other contract clauses
still require the unchanged original correctness verifier.

## Independent checks and boundaries

Counts 1, 2, 3 and 5 are checked against the original temporal oracle using the
prefix through frontier N-1; the remaining frontiers provably do no work. Count
259 uses literal anchors: frontier 0 returns `[0,1,514,515]`, frontier 1 returns
`[2,3,516,517]`, and frontier 256 returns `[512,513]`. Additional boundary counts
check the exact ordered partition and absence of missing/duplicate blocks.
The expensive temporal oracle is never run on a large benchmark workload.

Run `python -m pytest -q test_benchmark.py`. If the original bundle is relocated,
set `KV_FROZEN_ORACLE` to its verified `oracle.py` path. The manifest records
content identities rather than machine-specific paths.

No timing data was examined and no speed/quality gate is added here. This
supplement freezes expected outputs only, not a performance comparison or model
effectiveness conclusion. Altering the protected workload requires an explicit
new supplemental version and independently justified expectations before timing.
