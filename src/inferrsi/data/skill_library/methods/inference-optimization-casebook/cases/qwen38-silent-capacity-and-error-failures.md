# Three ways an inference server reported success while failing

Kind, origin, state and source identities belong to the
[typed source and scope record](qwen38-silent-capacity-and-error-failures.json).

While measuring a single-request engine through its OpenAI-compatible HTTP
endpoint, three distinct failures produced no actionable evidence: two returned
a success status, one returned an empty error body. Each is cheap to detect and
each cost a debugging round.

| Symptom | What actually happened | Detection that would have caught it |
| --- | --- | --- |
| HTTP 200 with an SSE `error` frame mid-stream | Decode ran past the configured graph bucket, the engine fell back or failed, and the wrapper kept the stream open | On every request, parse each SSE frame, reject an embedded `error` or a truncated stream, and require a terminal frame whose `finish_reason` is `stop` or `length`. When usage is present, check `completion_tokens` against it. A normal EOS/`stop` finish below `max_tokens` is success. Assert `completion_tokens` equals a frozen budget and `finish_reason == length` only on a capacity fixture that disables early stop |
| HTTP 400, empty body, 0-byte server log | The error handler deliberately dropped all exceptions ("client addresses and arbitrary exceptions do not belong in service logs") | Log a structured line with exception type and a truncated message; never return an error status without a body |
| Generation failed at token 993 with no message | The graph bucket was chosen from `prompt + headroom` with `headroom = 256`, while the request asked for 2048 output tokens | Validate bucket coverage against maximum output length, not against prompt slack, before starting the run |

Disposition: a serving layer must never convert an internal failure into a
success response. Log the exception type to stderr even when the payload must be
redacted, return a JSON error body for every 4xx/5xx, and treat capacity
(bucket, context, output length) as a pre-flight assertion rather than a runtime
surprise. `max_tokens` is an upper bound. Do not treat a shorter `stop` finish
as a failed length request.

Revisit condition: any wrapper that owns stream framing or error translation.
First check: send one request whose output length exceeds the configured
capacity and confirm the client sees a non-2xx status with a body.

Applicability: OpenAI-compatible serving wrappers over a custom engine, any
device. The third row is specific to bucketed graph execution.

Limitations: observed on one engine and one card; the exact fallback behaviour
past capacity was not characterised beyond "generation failed".

Retained records, with digests in the typed record:
[Issue #67](https://github.com/InferMatrixLab/InferRSI/issues/67);
the empty-log handler in
[nanovllm/qwen38/server.py](https://github.com/jiangkuaixue123/nano-vllm/blob/f2d1adc96a7e25e2e61425f5fa97a8f7a7225e77/nanovllm/qwen38/server.py);
`graph_headroom = 256` in
[nanovllm/qwen38/runner.py](https://github.com/jiangkuaixue123/nano-vllm/blob/3f7516a7b4a2c0a34871a453c294bc23b1b6c67c/nanovllm/qwen38/runner.py);
[nano-vllm pull request 8](https://github.com/jiangkuaixue123/nano-vllm/pull/8),
where job 1951 fails after 876 tokens and a streamed error is reported as
success; and the later headroom note in
[preparation.md](https://github.com/InferMatrixLab/InferRSI/blob/d5e17195280249cd0bbd5ef87d79d8654cce7056/evidence/qwen38-h20-fp8-single-request-vllm032/results/full-context-graph/preparation.md).
The literal index 993 is not in those artifacts.
