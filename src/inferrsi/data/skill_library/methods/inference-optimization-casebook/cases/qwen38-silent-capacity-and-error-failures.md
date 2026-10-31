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
