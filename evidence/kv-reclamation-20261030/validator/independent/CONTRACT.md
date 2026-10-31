# Synthetic CPU KV-block reclamation contract, version 1

This is a newly authored **synthetic** deterministic CPU task. It is not a
historical held-out bug, upstream reproduction, GPU experiment, service-level
benchmark, or evidence of model/knowledge effectiveness. The independent
verifier was authored before the optimized reference control and without
reading `audit-vllm-kv-lifetimes` or a target solution.

## Candidate interface

`candidate.py` exports a no-argument `Reclaimer` class. A fresh instance starts
with no leases and processed frontier -1. Its public methods are:

- `apply(event: dict) -> list[int]`: accept one event and return all block IDs
  newly reclaimed by that event, in the order defined below.
- `pending() -> list[tuple[str, int, tuple[int, ...]]]`: all unreclaimed leases,
  including unfinished leases, in original allocation order. Each tuple is
  `(request_id, generation, blocks)`; each block tuple preserves allocation order.

Inputs use JSON-compatible built-in values. Integers exclude booleans and floats.
The contract does not specify behavior for Python subclasses or concurrent calls.
Request IDs are strings; the empty string is valid. All integer fields are
nonnegative. `save_required` must be a boolean. The exact event key sets are:

| op | Other keys |
| --- | --- |
| `allocate` | `request_id`, `generation`, `blocks`, `write_step`, `save_required` |
| `finish` | `request_id`, `generation` |
| `save_complete` | `request_id`, `generation` |
| `advance` | `processed_step` |

An allocation's `blocks` is a nonempty list of distinct integer block IDs.
Block IDs cannot overlap any unreclaimed lease. A request ID cannot have two
unreclaimed leases. Once its previous lease is reclaimed, the request ID may be
reallocated only with a strictly greater generation than every previous
allocation of that request. Block IDs may be reused after reclamation, including
by another request. Generation gaps are valid.

`advance` moves the processed frontier to `processed_step`. Equal frontiers are
valid; decreasing frontiers are invalid. `finish` marks its matching active
lease finished. `save_complete` marks its matching active lease's asynchronous
save complete; it may arrive before `finish`. Duplicate notifications are
idempotent. Well-formed notifications for unknown, future, or reclaimed
`(request_id, generation)` pairs are ignored, not remembered for a later lease.
The full pair identifies a lifecycle: stale signals must not transfer across
request or block reuse.

## Reclamation and order

A lease is reclaimed if and only if all three predicates hold after a valid event:

1. Its matching `finish` was accepted after allocation.
2. It does not require a save, **or** its matching `save_complete` was accepted
   after allocation.
3. Its `write_step` is less than or equal to the processed frontier.

Every `apply` returns **all** newly ready leases, with no head-of-line blocking.
Within the returned list, leases follow allocation order and each lease's blocks
follow their supplied order. Unreclaimed leases retain their allocation order.
Readiness, removal from `pending`, and return of blocks are one operation. Each
allocation's blocks are returned exactly once during that lifecycle. Reusing a
block in a new lifecycle may correctly return the same numeric block ID again.
Neither enqueue nor a notification alone establishes readiness. Empty queues and
repeated `pending` calls are valid; empty/repeated valid events return `[]` when
they make no lease newly ready.

## Invalid events and atomicity

Non-dictionaries, missing/extra keys, unknown/non-string operations, wrong value
types, negative integer fields, empty/duplicate blocks, allocation conflicts,
non-increasing generations for reused requests, and a decreasing frontier raise
`ValueError`. Validate structure even for notifications that would otherwise be
ignored. Invalid events do not drain, advance, allocate, record notification
state, or alter generation history. `pending()` and all later valid event
results must be exactly as though the invalid call never happened.

## Scope and evaluation

No refcounts, shared blocks, cancellation, timeouts, real asynchronous workers,
threads, byte contents, GPU/API/provider calls, resource-capacity policies,
production compatibility, or wall-clock speed threshold are required. The
optimization target is queue draining under this contract, not a mandated data
structure or complexity. Correctness uses event-wise output and pending-state
equality, including invalid-call follow-through. A separate performance study
requires separately frozen workload, budget, and gates; these tests do not
establish a performance gain.

Development and grader traces have disjoint names and frozen bytes. All
requirements above are candidate-visible; exact grader cases are evaluator-only.
The trusted oracle recomputes state from accepted event history using temporal
predicates, rather than implementing the optimized queue. Neither oracle,
expected outputs, control tables, nor grader fixture files may be mounted into
an untrusted candidate sandbox. The direct-import verifier path is only for
trusted controls. Candidate subprocess transport must check the specified return
types before JSON conversion, which would otherwise erase tuple/list differences.

The positive replay control establishes verifier plumbing, not a general
algorithm. Negative replay controls alter one observable obligation at a time;
their rejection establishes specified sensitivity, not exhaustive proof that
every conceivable faulty implementation is rejected.
