# Cross-cutting diagnosis and stop conditions

| Symptom | Distinguishing check | Safe response / boundary |
| --- | --- | --- |
| Version label or build header disagrees | Compare full source SHA, VERSION, CMake project metadata and active guard | Keep all identities; never infer support from stale comments or silently relabel the executable |
| Generic setup appears convenient | Determine download/build/packing/calibration/service and RAM-pinning effects first | Do not run setup merely to inspect a package; require separate resource/host authorization |
| CMake tries to fetch a dependency | Native-experts/FetchContent and toolkit configuration are real build dependencies | Do not treat a disabled dependency slice or a direct CPU policy test as a complete engine build |
| Test discovery finds nothing | Check explicit registration/default-off and required pack/device conditions | Missing registration is not a test pass |
| GPU test exits zero with a skip | Require actual backend execution/result, not only exit status | Keep required backend blocked; do not invent a CPU equivalent |
| Same tier name or nominal bits seems interchangeable | Identify family, tensor format/geometry, representation and assets | Route model-runtime; do not force incompatible weight loading or slot restoration |
| Capacity is inconsistent | Separate physical unified pool from discrete devices and per-request/native state | Use bounded arithmetic to explain the ledger, not to certify real memory fit |
| API history or cache hint is mistaken for persistence/isolation | Identify history owner, native prefix/image state, process and backend completion | Route serving-state; no automatic replay of side-effecting tools or untrusted slots |
| A controller/helper reports success | Identify which production callsite and exact evidence level it tests | Route qualification; simulations and schemas do not prove GLM/DS4/MM3/Qwen runtime behavior |
| A source report claims a gain or high token agreement | Preserve model/runtime/workload/sampling/timing boundaries and negatives | Do not convert it to a universal ranking, lossless quantization or service PASS |
| Model or third-party rights are unclear | Read the distinct source/asset notice for the exact bytes | Stop asset acquisition/redistribution; root MIT and NO_LICENSE fallback answer different questions |

Native readiness requires the actual supported device/runtime/model resources.
No helper in this folder repairs a host, contacts a service or resolves missing
weights. Report unavailable stages explicitly rather than expanding installation
or accepting a partial check as complete verification.
