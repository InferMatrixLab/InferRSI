# Cache identity and stop ownership

IDs refer to [source-map.md](source-map.md).

`make_prompt_cache` defers to `model.make_cache` when available. Otherwise it creates per-layer KVCache, or RotatingKVCache with the configured maximum. Do not override a model's cache contract merely because a different model uses ordinary KV tensors (C1).

KVCache's logical offset is distinct from capacity: storage grows in blocks, returned views end at the logical offset, and trimming reduces that offset. This does not prove that trimming returns physical memory immediately. BatchKVCache filters keys, values, offsets and left padding together, and may remove shared left padding (C1).

The server resolves model/adapter/draft-model paths into its model key; prompt-cache lookup also consumes the token prefix (vision has a separate key path outside this skill's verified scope). LRUPromptCache returns deep copies for exact/shorter matches; reuse from a longer prefix needs trimmability and leaves a suffix for processing. Insertion updates count/byte accounting, removes redundant trimmable prefixes and evicts under limits (C2/C3). Path identity is not a content hash: pin actual model/tokenizer/adapter contents before comparing experiments.

Handler cleanup sets `_should_stop`. In batched generation the generation loop observes the flag, shares removal UIDs where applicable and removes their stage/row state; normal token/text completion can retain cache via a different branch. Single generation checks the flag after a response and then still reaches cache insertion; its distributed stop branch raises NotImplementedError (G4/G5). Do not promise immediate cancellation during prefill or cancellation of already submitted MLX kernels from this flag.

`BatchGenerator.close` restores a changed wired-memory limit after synchronizing its stream; it is not itself the same operation as removing one request or destroying all cache state. Model/cache destruction on the server generation thread is a separate shutdown path (G4).
