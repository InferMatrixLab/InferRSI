# Troubleshooting by discriminating check

Use the [semantic contracts](semantic-contracts.md) and exact
[source readset](source-notes.md). These are source-derived hypotheses and
checks, not observed native failures.

| Symptom or misleading observation | Distinguish first | Smallest safe next step / stop |
| --- | --- | --- |
| Bench command says20 steps/45 layers/reuse2/SSD but `--fasth3` selected | Requested versus normalized4/50/1/SSD0; reuse-step env is irrelevant at reuse1 | Run the bundled selected-field audit on an explicit declaration; do not label this an SSD-residency result |
| FastH3 still attempts reduced tokens | Ambient token enable versus normalized parameter0; range parsing versus forward-disable presence | Record selected token keys, remove unsupported enable from a separately approved command; do not run generation just to prove a known configuration conflict |
| `H3_DISABLE_FASTH3_SPARSE=0` unexpectedly selects dense fine | Key presence, not truthy value | Omit the key to request sparse; actual pipeline still needs native evidence |
| Sparse unavailable on a supposedly supported machine | Actual pipeline compilation/registration, disable keys, native dimension/range/memory guards | Keep unknown/blocked; source device-name heuristic is not qualification; fallback retains gated coarse |
| Disabling sparse changes timing or outputs | Dense fine+coarse versus sparse fine+coarse, not baseline H3 | First establish membership/rounding/layout contracts; any timing/quality comparison needs separate frozen native evidence |
| Same shape but checkpoint port is wrong | Per-head QKV interleave and FC1 half ordering before quantization | Use fixed label probes; only an authorized real-weight/native numerical comparison can establish parity |
| All names match, but schedule setup fails | Directory substring and time-weight key detector disagree; BF16 versus original F32 path | Inspect intended key family/config and mixed-shard identity without fetching payloads; stop on ambiguity |
| Missing `rope.inv_freq` | Intentional FastH3 generation versus wrong architecture/config | Verify declared architecture and coordinate/spatial-scale dependencies; do not synthesize arbitrary missing tensors |
| Off-by-one top-k or edge artifacts suspected | Double ceil vs float32; real partial counts vs padded64; dense prefix vs video ranking | Use120-tile rounding and5×5×5-token edge counterexamples; do not claim kernel correctness from arithmetic |
| Omitted row-FC2 flag assumed to restore grouped FC2 | FastH3 forces the selector inside selected int8 fused-MLP branch | Record actual MLP dispatch and BF16 controls, not just CLI flag absence |
| `make test` green but FastH3 parity claimed | Fixture skips, coarse-only VSA test and original 20-step schedule fixture | Preserve actual skipped/not_run scope; sparse fine and FastH3 schedule need explicit native cases |
| Key-map report shows no mismatch | Report provenance versus current code; skipped empty schemas and shape-only checks | Treat as schema-analysis lead, not converter/dtype/payload proof; do not execute remote curl helper |
| Need install/build on non-Apple host | Makefile links Apple frameworks; host helper imports Accelerate | Stop native preparation; no stub/mock replacement or backend-pass claim; package audit remains separately usable |

The offline helper fails malformed declarations with JSON stderr/exit2. Unknown
fields are rejected rather than silently ignored. An `issues` entry with exit0
is a finding, not successful engine validation. If a requested field falls
outside this selected schema, keep it in the human audit ledger rather than
loosening native or campaign gates to make the helper accept it.
