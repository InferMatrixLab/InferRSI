# Validation: bound windowed-attention replay

Nothing below has been run. This file records what would establish or refute each claim in `SKILL.md`.

## Static and CPU checks

| # | Check | Refutes if |
|---|---|---|
| V1 | Derive the dependency closure: for every consumer layer, list what it reads and where that was produced | Any consumer reads state whose value depends on tokens outside the retained region and no full-length copy of it is preserved |
| V2 | Confirm a full-length KV write exists at the boundary, independent of the compact query | No full-length write exists, so shortening the query changes the persistent cache |
| V3 | Confirm the retain rule is enforced wherever the value can enter, including model metadata, worker setup and metadata construction | The rule is enforced in fewer places than the value can arrive through, so a misconfiguration fails numerically rather than loudly |
| V4 | Confirm the checks are guarded by the truncation mode, so they do not fire when truncation is disabled | The checks fire in the disabled path, or `keep_tokens = 0` is accepted while truncation is on |
| V5 | Confirm the rollback floor is `max(configured, speculation_width + 1)` | The floor can be configured below the speculation width, allowing a short window after rollback |
| V6 | Recompute the visible-region formula and compare against the source expression, including the `valid_start` clamp and the empty-region representation | The clamp is absent or different, so zero-state recompute can attend cleared slots |
| V7 | Confirm `mask` mode produces the same visible-key set as `compact` mode on the same input, at a synthetic chunk boundary | The two modes disagree, so `mask` is not a valid reference |
| V8 | Confirm the boundary returns both a compact copy and the original full representation, and that the full one is stored | Only the compact copy survives the boundary, which corrupts the full-length KV write |
| V9 | Confirm the ring length is `window + rollback` per sequence and zero when the model has no SWA layers | The ring is short, so a rollback loses history |
| V10 | Confirm `PREFILL_STORE_EXTRA_STATE` gates both kvstore-ring additions; within that branch the keep margin also requires truncation mode not `off` | A keep margin is added without both gates, or a store-granularity margin is added while extra-state is disabled |
| V11 | Read the hyperconnection state bundle and confirm where its tensors live | The bundle is host-resident, which would make the gather reason different from field structure |
| V12 | Confirm the prompt-logprob behaviour is forced-off-with-warning rather than rejection | The engine rejects, or returns wrong values instead of doing either |

## Single-device checks

| # | Check | Refutes if |
|---|---|---|
| G1 | Metadata equivalence at chunk boundaries: visible-key sets, store slots and compressed-key ranges identical between `mask` and `compact` | Any of the three differ, which is a silent correctness bug |
| G2 | End-to-end equivalence on a fixed teacher-forcing trajectory: logprobs and top-k element-wise | Divergence outside tolerance |
| G3 | Chunk-boundary sweep: chunk sizes that do and do not align with store granularity | A boundary case diverges only when chunks do not align |
| G4 | Fully clipped chunk: a chunk entirely before the retained rectangle | The run crashes or produces no sampling position |
| G5 | Preemption count during the comparison run | Non-zero, which makes the run incomparable and any divergence uninterpretable |
| G6 | Prompt-logprob request under truncation: record whether it is forced off, warned about, or rejected | The observed behaviour differs from what the engine claims, or per-token values are returned for the clipped region |
| G7 | Measure the `compact` saving against the `mask` baseline, reporting both | `compact` shows no compute difference from `mask`, so the saving claim is empty |
| G8 | Peak memory at fixed context length, truncation on versus off, with the same declared resource budget | Required state is missing or the declared memory budget is exceeded; query compaction alone does not promise lower persistent-KV memory |
| G9 | A dependency-probe model: keep all historical keys, shorten only the query, and confirm output equality | Shortening the query alone changes the output, which would mean the procedure is not separable from key retention |

## What a PASS would require

V1 and G9 establish the architectural precondition, then G1 and G2 together establish equivalence, with G5 confirming no preemption. G1 alone is a metadata argument; G2 alone hides where a divergence came from.

G9 is the check that decides transfer. It separates "the query was shortened" from "the keys were dropped", which is exactly the distinction this procedure depends on and the one most likely to be collapsed when the same idea is applied to another stack.

## What this skill must not claim

- No general applicability to arbitrary sliding-window stacks. The dependency closure has to be derived for the target model.
- No optimization from `mask` mode; it is compute-neutral by construction.
- No prompt-logprob support for clipped regions.
- No claim that compaction implies dropped historical keys. Query-row compaction and historical-key retention are separate decisions.
- No bit-identical results across preemption; recompute moves the anchor.
