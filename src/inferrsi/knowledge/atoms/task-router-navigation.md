# Choose an inference task

Choose one primary skill by the requested deliverable. Load its full procedure
before the first supporting evidence search. Record secondary tasks for follow-up.
The route cards remain available to callers that consume the JSON summaries.

| Primary skill | Choose it when | Route card |
| --- | --- | --- |
| `task-day-0` | First usable support for a new checkpoint or model architecture in an existing engine. | [day0-model](references/routes/day0-model.json) |
| `task-performance` | A correct baseline misses a specified latency, throughput, memory or cost objective. | [performance](references/routes/performance.json) |
| `task-debug` | A hang, crash, OOM or execution-path failure needs a reproducible cause. | [debug](references/routes/debug.json) |
| `task-accuracy` | Inference completes but output violates a reference, quality metric or tolerance. | [accuracy](references/routes/accuracy.json) |
| `task-version-alignment` | A dependency or engine upgrade must preserve API, ABI, operator or runtime behavior across a stack. | [version-align](references/routes/version-align.json) |
| `task-derived-engine` | The deliverable reuses the execution core of vLLM, vLLM-Omni or another pinned parent, as in a DeepInfer-like extension. | [derived-engine](references/routes/derived-engine.json) |
| `task-independent-engine` | A new runtime must own execution, memory and device integration on a distinct OS, model or hardware stack. | [independent-engine](references/routes/independent-engine.json) |

