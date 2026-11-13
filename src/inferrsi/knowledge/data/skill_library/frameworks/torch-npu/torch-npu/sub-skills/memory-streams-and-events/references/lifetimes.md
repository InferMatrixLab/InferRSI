# Ordering and ownership

## Two independent obligations

For a tensor produced on stream A and consumed on B, use a dependency such as
`B.wait_stream(A)` before the consumer. For storage whose owner may release it
while B is still using it, use supported `tensor.record_stream(B)` or keep an
explicit lifetime until completion. `record_stream` records allocator use;
it does not order the producer's computation. A wait orders future work;
it does not itself transfer Python storage ownership. The bundled stream case
shows both edges with small tensors.

```python
producer = torch.npu.current_stream()
consumer = torch.npu.Stream()
x = torch.ones(8, device="npu")
consumer.wait_stream(producer)
with torch.npu.stream(consumer):
    y = x * 3
    x.record_stream(consumer)
producer.wait_stream(consumer)
assert torch.equal(y.cpu(), torch.full((8,), 3.0))
```

The host read is the verification boundary. Retain tensor references until
the intended completion point; only then investigate cache behavior. This
example is a deterministic ordering demonstration, not an allocator stress test.

## Allocator mechanism

The inspected `DeviceCachingAllocator::free` clears allocated state and
allocated-byte accounting before memory necessarily becomes reusable. Recorded
cross-stream uses insert events; the reaper queries events and decrements each
block's event count, returning it to the pool only at zero. During capture,
end-of-life events are deferred to a later non-capture phase. `recordStream`
stores use-stream membership. This separates free-requested, reusable cache
and returned-to-runtime states (F8).

Do not treat the opening allocator overview's example split threshold as a
universal tuning constant. Actual policies depend on the selected configuration
and implementation. Preserve defaults until a bounded reproduction establishes
fragmentation; change one startup option per fresh process and compare correct
results at matching completion boundaries. `empty_cache()` cannot free live
tensors. Graph/private pools and imported/custom allocations require their own
owner analysis. For detailed policy experiments use the existing focused owners.

Pinned-host `record_event` validates that the pointer/context belongs to its
tracked allocator before adding the stream. Arbitrary externally pinned memory
does not acquire this lifecycle automatically (F9). A nonblocking host-to-device
copy does not permit early mutation/reuse of its host buffer. Keep its storage
until the copy's stream completes; measure host RAM separately from device HBM.

## Event and task-queue boundaries

`Stream.wait_stream` is implemented through a recorded event and affects future
work without blocking the host. Events are created lazily, bind to a device at
first record and reject recording on a different device's stream. The C++ event
query accounts for host task-queue delivery before consulting device completion;
a host enqueue is not a completed kernel. Event destruction is deferred and
exceptions in the destructor are swallowed. Time events only when enabled for
timing and use an explicit completion boundary (F10).

Current streams are thread-local selections over per-device stream internals;
a different Python thread or device needs its own correct guard. Stream IDs,
pool-size constants and external-stream encodings are implementation details,
not application allocation APIs. External streams do not own the external
resource's lifetime and several event/graph operations explicitly reject them.

## Diagnostic output

Return columns for allocation owner, aliases, allocating stream, using stream,
ordering edge, lifetime retention and completion observation. Record
`memory_allocated`, `memory_reserved`, selected `memory_stats` counters and
host metrics at the same phase. A fall in allocated bytes with unchanged
reserved bytes may be cache retention, not a leak. A missing backend keeps all
device-timing and allocator-efficacy conclusions blocked.
