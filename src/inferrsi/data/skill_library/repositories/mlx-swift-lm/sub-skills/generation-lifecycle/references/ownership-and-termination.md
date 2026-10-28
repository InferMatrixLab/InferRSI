# Source ownership and termination contract

These mechanisms come from pinned mlx-swift-lm source, not an executed Swift
API inspection. Application code must use its actual overload and resolved
dependency/build artifacts; analogous names do not establish equivalent lifetime.

## Container access is not whole-stream serialization

[`ModelContainer`](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Libraries/MLXLMCommon/ModelContainer.swift#L32-L261)
is a final Sendable class wrapping `SerialAccessContainer<ModelContext>`.
[`AsyncMutex`](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Libraries/MLXLMCommon/Utilities/SerialAccessContainer.swift#L1-L68)
holds a logical lock across the entire async body, using FIFO checked
continuations and deferred unlock. An actor alone releases isolation at awaits;
this explicit lock preserves exclusive access across those suspension points.
The inspected waiters have no cancellation-removal handler. Do not promise that
cancelling a waiting caller immediately removes/preempts its queued operation.

`perform` operates under this lock. Its source warns that MLXArray is not
Sendable and requires evaluation before returning; return a genuinely Sendable
conversion or use a deliberate ownership transfer, not concurrent sharing of
lazy array references. `SendableBox` is package-private, unchecked and
single-consume: it clears its optional value and fatal-errors on double consume.
It is neither a public wrapper nor a deep copy that makes sharing safe.

`prepare` retrieves the Sendable processor through the container, then awaits
processor preparation outside that lock. `generate` transfers its LMInput,
discovers pending components under a context read, loads them outside that read,
then enters a context read to construct generation. The source comment limits
exclusive visitation to prefill/startup and permits concurrent reads of already
evaluated weights afterward. This does not authorize concurrent weight mutation
or reuse of the same mutable cache by several generations.

`ModelContext` is a non-Sendable value holding model, processor, tokenizer and
configuration; its initializer sets the model to evaluation mode. The processor
and tokenizer protocols are Sendable. These boundaries do not imply that every
object reachable through the model can safely escape into arbitrary tasks.

## Iterator preparation and lookahead already own work

[`TokenIterator`](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Libraries/MLXLMCommon/Evaluate.swift#L970-L1199)
validates its cache plan/components and prepares the prompt in its initializer.
Preparation commits processed prompt positions and primes the next token with
`asyncEval` before the producer Task is created. Immediate cancellation of that
later task does not undo preparation.

`next()` first tests its token limit. Otherwise it saves the previous token,
executes the next model step, advances cache/state and schedules evaluation of
the next token plus cache state and optional log-probability arrays. Only then
does it increment its count and return the previous token's scalar value.
Thus observing a token is not the boundary before all work for the following
token. The source also uses per-step autoreleasepool and periodically clears
freed MLX cache buffers; neither mechanism proves a fixed memory bound or fit.

## Producer owns iteration through cleanup

The public
[`generateLoopTask`](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Libraries/MLXLMCommon/Evaluate.swift#L2691-L2910)
wrapper at line 2695 delegates to a private generic collector overload at line
2715. That private implementation moves iterator/handler into a normal Task
through single-consume boxes; it is not an additional public API. A new
[`GenerationWorker`](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Libraries/MLXLMCommon/Utilities/GenerationWorker.swift)
uses a per-generation DispatchSerialQueue-backed executor with a synchronous
body. Blocking MLX iteration and cleanup do not occupy Swift's cooperative
pool. The task context and cancellation still belong to that producer; this is
not a detached global worker serializing every generation. Optional wired ticket
scope wraps the worker; the underlying ticket manager belongs to the MLX
dependency, not this source's container.

The relevant order is:

1. Check `!Task.isCancelled` **before** entering `iterator.next()`.
2. Process returned token/handler dispositions, or leave on nil/stop/cancellation.
3. Finalize capable iterators, writing the existential-cast value back because
   reconciliation can change inline state as well as referenced caches.
4. Run handler end processing and build/yield final info.
5. Synchronize `Stream.defaultStream`.
6. Finish the continuation and return collector results from worker/ticket scope.
7. Producer task value becomes available to its awaiting owner.

Cancellation during an already-entered `next()` cannot preempt its synchronous
body. Source tests deliberately permit that step's token before finalization.
`continuation.onTermination` cancels the producer only for `.cancelled`, not
normal `.finished`. A consumer ending iteration can request termination without
having joined the producer. If the consumer is gone, final info may not be
observable. Receiving info is earlier than synchronization; awaiting the
producer is the deterministic source-level resource-lifetime boundary.

This synchronizes the source's **MLX default stream**, not arbitrary external
GPU queues/streams. No timing bound, universal OS-backgrounding safety or native
device success follows from this source order.

## Stops, counts and finalization are separate observations

Stop IDs combine model EOS, tokenizer EOS, resolvable extra EOS strings and
handler-contributed boundaries; unknown-token handling also stops. The token
collector records a returned token before stop filtering, while public
generationTokenCount excludes a stop token unless includeStopToken requests its
inclusion. Text/tool chunks are not one-to-one tokens.

Without a reason from the handler/stop path, cancellation takes precedence over
a reached token limit; otherwise a reached iterator limit gives `.length`.
Handler end processing may convert a noncancelled reason to `.stop`, or report
`.cancelled`. A consumer cancellation after already-completed generation does
not retroactively require `.cancelled`. Records without ordering cannot decide
which event won.

The inspected
[`speculative finalizer`](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Libraries/MLXLMCommon/Evaluate.swift#L1664-L1697)
reconciles unreturned verified lookahead through storage rewind/trim and avoids
its trailing draft feed when cancelled. The full speculation/cache algorithm
is not covered by this lifecycle route. Finalization is not synonymous with
zero remaining work. The deprecated callback loop has a different
next-before-callback-stop order; do not apply the async loop's gate to it.

The ordinary async `generate` and `ModelContainer.generate` return only a
stream. Public `generateTask`, `generateLoopTask`, `generateTokensTask` and
`generateTokenTask` expose producer handles. There is no
`ModelContainer.synchronize()` in the inspected container API. Package-private
recording/protocol helpers and transfer/locking types are not substitutes for
public entry points in application code.
