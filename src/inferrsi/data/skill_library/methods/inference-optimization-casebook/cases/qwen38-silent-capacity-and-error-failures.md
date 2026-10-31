# Three ways an inference server reported success while failing

While measuring a single-request engine through its OpenAI-compatible HTTP
endpoint, three distinct failures produced no actionable evidence: two returned
a success status, one returned an empty error body. Each is cheap to detect and
each cost a debugging round.

| Symptom | What actually happened | Detection that would have caught it |
| --- | --- | --- |
| HTTP 200 with an SSE `error` frame mid-stream | Decode ran past the configured graph bucket, the engine fell back or failed, and the wrapper kept the stream open | Assert `completion_tokens` equals the requested count and `finish_reason == length` on every request |
| HTTP 400, empty body, 0-byte server log | The error handler deliberately dropped all exceptions ("client addresses and arbitrary exceptions do not belong in service logs") | Log a structured line with exception type and a truncated message; never return an error status without a body |
| Generation failed at token 993 with no message | The graph bucket was chosen from `prompt + headroom` with `headroom = 256`, while the request asked for 2048 output tokens | Validate bucket coverage against maximum output length, not against prompt slack, before starting the run |

Disposition: a serving layer must never convert an internal failure into a
success response. Log the exception type to stderr even when the payload must be
redacted, return a JSON error body for every 4xx/5xx, and treat capacity
(bucket, context, output length) as a pre-flight assertion rather than a runtime
surprise.

Revisit condition: any wrapper that owns stream framing or error translation.
First check: send one request whose output length exceeds the configured
capacity and confirm the client sees a non-2xx status with a body.

Applicability: OpenAI-compatible serving wrappers over a custom engine, any
device. The third row is specific to bucketed graph execution.

Limitations: observed on one engine and one card; the exact fallback behaviour
past capacity was not characterised beyond "generation failed".

Retained records: the empty-log handler is `nanovllm/qwen38/server.py` at
`f2d1adc96a7e25e2e61425f5fa97a8f7a7225e77`. `graph_headroom = 256` is
`nanovllm/qwen38/runner.py` at `3f7516a7b4a2c0a34871a453c294bc23b1b6c67c`.
[nano-vllm pull request 8](https://github.com/jiangkuaixue123/nano-vllm/pull/8)
(body sha256 `b4c5b6c2c3681976df2ccc7ea41c9b5c245aa0769d2c82e91e26f4eca8cc1684`)
records a streamed error reported as success and job 1951 failing after 876
tokens. Prompt+256 headroom on an 8192-input/2048-output request is retained in
`evidence/qwen38-h20-fp8-single-request-vllm032/results/full-context-graph/preparation.md`
at `d5e17195280249cd0bbd5ef87d79d8654cce7056`. The literal index 993 is not in
those artifacts.
