# Serving and cache failures

| Symptom | Inspect | Recovery or boundary |
| --- | --- | --- |
| Missing `config.json`/weight shard | Explicit local path, index and all named safetensors shards | Repair the selected local asset set outside this diagnostic. Do not fall through to network download. |
| `Incomplete weights.pack`, capacity, format or identity mismatch | Manifest/payload size, requested capacity, layout/backend, target/draft role and quantization | Select a valid compatible cache or separately rebuild into a new derived entry; do not weaken validation or delete live data. |
| Unexpected prefix miss | Exact token IDs including system/tool template; strict length; `min_tokens`, quota and disk identity | Expected miss should prefill. Similar text or equal-length input is not sufficient for a reusable prefix. |
| Stored entry drops / `StalePrefix` | Header/blob integrity, buffer names/sizes, StepState ABI and device/code/numerics identity | Preserve safe fallback to miss/shorter prefix before any GPU writes; compare outputs after prefill. |
| Disk tier disabled / `StoreBusy` | Single owner, private directory, quota and I/O error | Keep documented memory-only operation. Do not remove another process's lock or broaden directory permissions. |
| Prefix file appears queued but not durable | Submit result, writer completion, `flush` result and `contains` | Queue admission is not persistence. Bounded unload can release while queued writers finish. |
| Drift after recipe/sampling change | Adoption roles/sizes, exact weight windows, state reset and shared prefix identity | Compare with a clean compatible session. Pipeline identity is separate from sequence state. |
| HTTP 429 / queued Ollama request | Adapter admission path and current generation/load | Expected one-generation policy; do not advertise batching/concurrency. |
| HTTP 503 `model_load_failed` | Lifecycle state, failed attempt and waiting arrivals | Report failed load distinctly; later requests may retry. `/health` liveness is not loaded readiness. |
| Unload seems delayed / memory remains | Pending requests, GPU lock/in-flight work, engine references, host snapshots, CPU pipelines and OS file cache | Respect completion/lock boundary. Different memory owners survive differently; no forced teardown of active work. |

Full-model prefix resume, DSpark state, quality and complete HTTP performance
remain unverified until separately exercised with the selected assets/backend.
CPU/mock and disk-integrity checks do not clear those scopes.
