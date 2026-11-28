# Memory and event troubleshooting

| Symptom | Competing explanations | Check/recovery |
|---|---|---|
| Cross-stream wrong values | Missing producer dependency or early storage reuse | Add the proper wait and lifetime protection independently; compare synchronized results. |
| Deletion lowers allocated but not reserved | Pending events, cache, graph pool or fragmentation | Check active/reserved counters after completion and release owners before changing allocator options. |
| Pinned copy corrupted | Host buffer modified/released before copy completion | Retain host storage and wait for the copy's stream; inspect whether allocator tracking owns the pointer. |
| Event query false immediately after record | Host queue and device work may both be pending | Use event/stream synchronization at the required boundary; do not poll indefinitely. |
| Event device mismatch | Event bound to its first recording device | Create one event per required recording device and validate the intended cross-device operation. |
| Capture increases retained memory | Capture/private-pool ownership and deferred events | Inspect graph lifetimes through the graph route before calling it a leak. |
| External stream rejected | Operation explicitly excludes external streams | Use a supported managed stream or the external owner's correct synchronization contract. |

Do not erase stream records manually to force reuse. A sanitizer or CPU
reference cannot certify a particular backend allocator lifetime under load.
