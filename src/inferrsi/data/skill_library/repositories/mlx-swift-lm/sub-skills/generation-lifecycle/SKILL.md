---
name: generation-lifecycle
description: "Investigate mlx-swift-lm container and iterator ownership, cooperative cancellation, finalization and producer-task cleanup boundaries, then audit explicit caller evidence records without simulating Swift tasks or authenticating Metal execution."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
---

# Generation ownership and deterministic cleanup

Use this route for early stream termination, backgrounding/shutdown races,
unexpected work after cancellation, or claims that a completion event means
model/cache resources are reusable. This source-derived **candidate** gives an
investigation procedure, not native Swift/Metal qualification.

## Trace the actual ownership boundary

1. Record the source and actually resolved MLX dependency revisions, selected
   async API/overload, device/backend, model/tokenizer identity, cache owner and
   producer/consumer task handles. A dependency version range is not a resolved
   commit. Separate source knowledge from observed native execution.
2. Read [ownership and termination](references/ownership-and-termination.md).
   `ModelContainer` uses an explicit async mutex; an ordinary actor is not an
   equivalent replacement across suspension points. Container generation holds
   exclusive access for prefill/startup, **not** the complete stream lifetime.
3. Keep lazy MLX arrays and mutable caches in their intended ownership domain.
   Evaluating an array does not make it freely shareable. Package-private
   transfer/locking utilities are not public application APIs.
4. Identify which work was submitted before cancellation. Iterator construction
   already prepares the prompt. Each `next()` schedules the next token/cache
   state before returning the previous token. Checking cancellation before
   `next()` prevents entering another step once observed; it does not undo a
   currently executing step or previously submitted work.
5. For early-stop control, retain the producer task exposed by task-handle APIs,
   request cancellation when appropriate and observe its completed join before
   claiming deterministic producer cleanup. The ordinary stream-returning
   container API does not expose that handle. Do not invent a
   `ModelContainer.synchronize()` method.
6. Keep these observations distinct: iterator finalization, final info event,
   synchronization of the source's MLX default stream, stream finish and
   completed producer-task join. **Info is yielded before synchronization.**
   Neither an info event nor a cancellation request alone is a join. This is
   not a statement that every GPU stream in the process has been synchronized.
7. Use [native evidence boundaries](references/native-evidence.md) to select
   separately authorized evidence after whole-graph integration. Missing Swift,
   Xcode/MLX or actual Apple Metal evidence stays `BLOCKED_REQUIRED_BACKEND`;
   source inspection, CPU-control tests and helper output cannot replace it.

## Audit declared evidence, not task execution

From this sub-skill directory:

```bash
python scripts/audit_generation_evidence.py --example
python scripts/audit_generation_evidence.py observations.json
```

`--example` emits synthetic input; the file/stdin form audits records. Read the
[schema and limits](references/evidence-schema.md). The helper distinguishes
declared completed joins, ownership conflicts and unresolved cleanup evidence.
It executes no task, model or GPU, authenticates no observation, calculates no
performance result and returns no `PASS` verdict. A caller declaration is not
an instrumented native fact.

## Return separate conclusions

Report (1) source-supported ownership/ordering, (2) actual task/stream/native
observations and unresolved gaps, and (3) independent model/quality/service
evidence. Do not infer token counts from text chunks or infer a stop reason
from a consumer cancellation with unknown ordering. Use
[troubleshooting](references/troubleshooting.md) for info-before-sync, concurrent
generation, blocked work and missing completion events. Kernel numerical parity
belongs to [gated-delta contract](../gated-delta-contract/SKILL.md), not to a
successful cancellation record.
