# Usability case index

Sixteen difficult synthetic cases cover two per each primary sub-skill.
One root routing case and two integrated cases cover multi-route composition.
`updated-input-fork-join` derives from the native graph multi-stream test;
`hccl-amp-trace-state` is synthesized because no single small safe native test
combines HCCL completion, scale overflow and profiling on this unavailable
backend. Each case retains source evidence and explicit content assertions.
Native tests remain independently blocked; static assertion grading checks
content presence, not future-agent execution or hardware correctness.

| Case | Target | Basis | Coverage | Assertions |
|---|---|---|---|---|
| `sub-skills/installation-and-compatibility/release-versus-master` | installation-and-compatibility | synthetic | advanced / troubleshooting | 5 |
| `sub-skills/installation-and-compatibility/import-versus-device` | installation-and-compatibility | synthetic | advanced / troubleshooting | 4 |
| `sub-skills/privateuse1-and-dispatch/fallback-hidden-device-result` | privateuse1-and-dispatch | synthetic | advanced / troubleshooting | 5 |
| `sub-skills/privateuse1-and-dispatch/lazy-import-contract` | privateuse1-and-dispatch | synthetic | advanced / troubleshooting | 4 |
| `sub-skills/operator-development/broadcast-custom-gradient` | operator-development | synthetic | advanced / troubleshooting | 6 |
| `sub-skills/operator-development/missing-aclnn-symbol` | operator-development | synthetic | advanced / troubleshooting | 6 |
| `sub-skills/memory-streams-and-events/record-stream-is-not-ordering` | memory-streams-and-events | synthetic | advanced / troubleshooting | 5 |
| `sub-skills/memory-streams-and-events/external-pinned-owner` | memory-streams-and-events | synthetic | advanced / troubleshooting | 6 |
| `sub-skills/graph-and-compile/eager-fallback-masquerade` | graph-and-compile | synthetic | advanced / troubleshooting | 7 |
| `sub-skills/graph-and-compile/capture-pinned-queue-conflict` | graph-and-compile | synthetic | advanced / troubleshooting | 6 |
| `sub-skills/distributed-and-hccl/future-versus-completion` | distributed-and-hccl | synthetic | advanced / troubleshooting | 6 |
| `sub-skills/distributed-and-hccl/timeout-triage` | distributed-and-hccl | synthetic | advanced / troubleshooting | 6 |
| `sub-skills/training-and-precision/accumulation-clipping` | training-and-precision | synthetic | advanced / troubleshooting | 6 |
| `sub-skills/training-and-precision/bce-fused-resume` | training-and-precision | synthetic | advanced / troubleshooting | 6 |
| `sub-skills/profiling-and-debugging/empty-timeline-async-parse` | profiling-and-debugging | synthetic | advanced / troubleshooting | 6 |
| `sub-skills/profiling-and-debugging/blocking-invalidates-benchmark` | profiling-and-debugging | synthetic | advanced / troubleshooting | 6 |
| `root/novice-backend-and-routing` | torch-npu | synthetic | advanced / troubleshooting | 5 |
| `integration/updated-input-fork-join` | torch-npu | native-derived | advanced / troubleshooting | 6 |
| `integration/hccl-amp-trace-state` | torch-npu | synthetic-cross-capability | advanced / troubleshooting | 4 |

All cases contain user_request.txt, README.md and assertions.json. All eight
primary routes have native source evidence anchoring assertions. Long-tail
inventoried-only compiler/RPC/export/fault paths remain unvalidated and are
named in the gap register. JSON contract fixtures exercise safe helper error
recovery separately from these workflow prompts.
