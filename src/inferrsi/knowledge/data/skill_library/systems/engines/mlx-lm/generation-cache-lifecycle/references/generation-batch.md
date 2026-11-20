# Generation and batch state

IDs refer to [source-map.md](source-map.md).

Single generation: tokenize/validate → make model-specific/default cache → chunked prefill with explicit cache evaluation → final-prompt step → schedule next decode token with async_eval → read/yield current token → EOS/length → final detokenizer segment (G1). The next token may already be queued when the current token is yielded; yielded-token count and computation submitted are not identical boundaries.

BatchGenerator maintains pending sequences, a PromptProcessingBatch, a GenerationBatch and prompt-stage `_currently_processing`. `_next` performs existing decode work first; full completion capacity prevents further prompt work. Available capacity admits pending sequences, segments are consumed in bounded chunks, and prompt rows with only their final input move to generation (G2).

| Per-row state | Keep aligned during filter/remove |
|---|---|
| Identity/data | UID, token history, cache row, pending token/logprob |
| Generation configuration | sampler, logits processors, max token count, stop sequences |
| Progress | generated count, token context, stop matcher |
| Prompt processing | prompt batch and `_currently_processing` row indices |

Completion extracts the finished row's cache before filtering survivors. Explicit removal searches all three stages; a caller may request caches before removal (G2/G3). No request-level state should be inferred from a single tensor's length alone.

Server requests reach batching only through the server's actual gates (G5). Library batching support, a server thread and HTTP streaming are separate facts; none proves an arbitrary configuration batches or meets latency objectives.
