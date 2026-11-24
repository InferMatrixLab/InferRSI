# Measuring Hy4-Flash-FP8 decode at a fixed context length

The eight-device Ascend 950DT campaign uses LongBench v2 for decode latency and AIME2026 for answer quality. Both clients issue one request at a time. The acceptance issue records the image, checkpoint, deployment arguments, comparison gates and measured revisions. [Campaign and round ledger](https://github.com/InferMatrixLab/InferRSI/issues/613)

## Replaying identical prompts

Render each pinned LongBench ID with the published zero-shot template and the checkpoint tokenizer, with no added special tokens. Use the tokenizer offsets to locate the tokens wholly inside the document. Keep the instruction prefix, question, four choices and any tokens that overlap a document boundary once. Fill the remaining positions from the start of the document token sequence, cycling that sequence when more tokens are needed. This produces a deterministic token array and keeps the question at the end even when the document exceeds the budget. All twenty original prompts in this campaign required padding.

Send those IDs directly to the completions endpoint in the published order. Check the ordered request file digest before warmup and each measurement. Check each sample's token-ID digest, API-reported prompt length, generated-token count and completion reason. Dataset ID alone cannot distinguish a full-document prompt from its resized counterpart. [Input identities and reconstruction rule](https://github.com/InferMatrixLab/InferRSI/issues/613#issuecomment-7120848813)

## Measuring speculative output

Use a monotonic clock on the host loopback client. Record the timestamp and number of generated IDs in each SSE token event, along with the final usage receipt. Divide the interval from the first token event to the last by the actual output length minus one. Compute the median of the twenty per-request values with equal request weights. Keeping time to first token, chunk sizes and the stream completion timestamp makes a change in output buffering visible.

On an exclusive service, take snapshots of the engine's draft-round and accepted-draft-token counters immediately before and after each formal request. Dividing the client decode span by draft rounds gives an approximate round duration. Tokens delivered per round expose variation in acceptance. The two estimates help determine whether to investigate proposal/verification cost or acceptance. A rank-local diagnostic profile from an AIME decode can identify operators for investigation. A fixed-length performance trial is still needed to quantify any effect on the latency objective.

## Comparing revisions

Use one service identity for a round's warmup, formal timing and conditional AIME scoring. Apply the declared latency gain before invoking the expensive evaluator. Retain all predictions, and count a quality reference only when all thirty items have a completed evaluation. Preserve interrupted measurements with their original protocol and completion counts. A new service replays the selected revision, identical request bytes and scorer for the final check. [Service-reuse campaign lifecycle](service-reuse-campaigns.md)

## Locating a context-limit stall

With the combined input and output exactly equal to the serving context limit, aggregate TPOT hides where the delay occurs. On baseline `db557a38405b67c57a479d56b37662073b810a89`, all twenty fixed-length requests completed. Their P50 was 11.4392 ms/token. For each request, take the maximum SSE gap after delivery of at least 1,008 tokens and the maximum from tokens 32 through 1,007. The medians of those maxima were 637.57 ms and 46.11 ms, respectively. The raw timestamps preserve both intervals in the formal TPOT. This observation motivated testing extra serving-context capacity while replaying identical inputs and output caps. [Per-request baseline and hypothesis](https://github.com/InferMatrixLab/InferRSI/issues/613#issuecomment-7121157226)
