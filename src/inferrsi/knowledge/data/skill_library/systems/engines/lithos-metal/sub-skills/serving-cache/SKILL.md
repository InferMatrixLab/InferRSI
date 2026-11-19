---
name: serving-cache
description: "Audit Lithos Metal local serving, prepared-pack identity, exact target/draft prefix checkpoints, disk integrity, session adoption and idle release when startup, cache reuse or request isolation fails."
---

# Validate serving and cache ownership

## Trigger and evidence

Use for stale pack/prefix reuse, slow or failed startup, cache-resume drift,
HTTP state isolation, session replacement and idle reload. Source-derived
candidate; empirical validation **not_run**. Read the [root](../../SKILL.md),
[workflows and contracts](references/workflows.md) and
[source readset](../../references/source-notes.md).

Obtain selected target/draft revisions, checkpoint/pack manifests, tokenizer/chat
template identity, backend/config/recipe, context/prefill/numerical settings,
actual prompt token boundaries, tier/budget and load/unload/request trace.
Use placeholders for local paths and private prompt content in reports.

## Decision procedure

1. Separate checkpoint resolution, derived weight packs, CPU programs/pipelines,
   GPU session buffers and host/disk prefix snapshots. Each has a different
   validity key and lifetime. A pack hit is not a prefix hit or a model check.
2. Validate local assets and prepared packs before serving. Check architecture,
   all shards, context capacity, layouts/formats, selected quantization and
   manifest ranges. Preserve a reported mismatch; do not reuse or repair an
   incompatible cache silently. File size/mtime identity is not weight-byte
   authentication.
3. Trace tokenizer/template input through system messages, tools and history to
   exact token IDs. Prefix matching uses the longest **strict** matching prefix,
   leaving at least one input token for final prefill/logits. Equivalent text,
   a changed tool schema or an exact-length request is not automatically a hit.
4. Check a snapshot's StepState, live target/draft attention rows and complete
   recurrent slots before any restore writes. Worker counters and per-round
   proposal scratch are not sequence checkpoints. For disk, also check identity,
   lengths/names/ranges and per-blob hashes; incompatible/corrupt entries fall
   back to prefill.
5. On session/recipe/sampling changes, inspect buffer adoption and state reset.
   Only selected GPU buffers remain resident; CPU programs and executable
   pipelines can survive. Same-named differently packed weights cannot be
   shared blindly. Distinguish reuse of allocation from reuse of sequence state.
6. Trace pending arrival → GPU lock → load/generation/stream → completion before
   idle release. Unload waits for active GPU work, releases engines/GPU
   allocations, attempts a bounded flush of optional disk copies, then clears
   host snapshots.
   A stalled writer can finish later; release does not imply every entry was
   persisted. Reload can reuse code/pipelines and disk prefixes independently.
7. Check HTTP contracts with mocks and tiny temporary cache fixtures first.
   Then qualify actual model cache resume, reload and stream cancellation on
   the selected backend before measuring complete-request latency or stability.

## Counter-signals and outputs

Cache misses after a changed identity, strict-prefix exclusion or quota eviction
are expected. Prefix-store lock contention can leave a server using memory-only
snapshots. Health liveness, warmup completion, pack validity and numerical
continuation are separate observations. Unified memory does not make host
snapshots, GPU allocations and OS file-cache pages interchangeable accounting.

Return a cache/lifecycle ownership ledger, hit-or-miss reason, earliest invalid
boundary, safe fallback and unresolved qualification. Read
[troubleshooting](references/troubleshooting.md) before deleting anything or
changing capacity. No live server, downloads, cache deletion or network exposure
is authorized by reading this procedure.
