# MLX-LM source map

Source: [ml-explore/mlx-lm](https://github.com/ml-explore/mlx-lm/tree/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02), revision `ab7f7048dc341ced2d84b1887eeb17d60b0d1b02`. Inspected on 2026-10-21. Copyright © 2023 Apple Inc.; [MIT license](https://github.com/ml-explore/mlx-lm/blob/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02/LICENSE). This bounded source readset does not qualify the installed API or model/backend combination.

CODE is an implementation observation; TEST-SOURCE is an unexecuted upstream assertion. The diagnostic steps are HYPOTHESIS until applied to a matching workload.

| ID | Class | Pinned path/symbol | Observation |
|---|---|---|---|
| G1 | CODE | [generate_step L388-L493](https://github.com/ml-explore/mlx-lm/blob/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02/mlx_lm/generate.py#L388-L493); [stream_generate L707-L782](https://github.com/ml-explore/mlx-lm/blob/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02/mlx_lm/generate.py#L707-L782) | Prefill evaluates cache state; decode uses its generation stream and async submission; stream wrapper handles tokenization/EOS/length/final text. |
| G2 | CODE | [BatchGenerator._next/next L1866-L1967](https://github.com/ml-explore/mlx-lm/blob/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02/mlx_lm/generate.py#L1866-L1967); [GenerationBatch.filter/next L1502-L1573](https://github.com/ml-explore/mlx-lm/blob/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02/mlx_lm/generate.py#L1502-L1573) | Decode runs first, capacity gates prompt admission, and completion filters all per-row generation state. |
| G3 | CODE | [BatchGenerator._find_uids/remove L1767-L1823](https://github.com/ml-explore/mlx-lm/blob/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02/mlx_lm/generate.py#L1767-L1823) | UID lookup spans pending/prompt/generation; prompt removal also filters `_currently_processing`. |
| G4 | CODE | [GenerationContext.stop L318-L332](https://github.com/ml-explore/mlx-lm/blob/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02/mlx_lm/server.py#L318-L332); [batch stop/removal L1014-L1042](https://github.com/ml-explore/mlx-lm/blob/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02/mlx_lm/server.py#L1014-L1042); [handler finally L1705-L1706](https://github.com/ml-explore/mlx-lm/blob/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02/mlx_lm/server.py#L1705-L1706) | Context stop is a flag; batch loop propagates UID removal; generation-thread exit resets the model/cache. |
| G5 | CODE | [server batching gate L766-L771](https://github.com/ml-explore/mlx-lm/blob/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02/mlx_lm/server.py#L766-L771); [single path L1144-L1157](https://github.com/ml-explore/mlx-lm/blob/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02/mlx_lm/server.py#L1144-L1157) | Seed/KV quantization constrain batching; single-request stop still reaches cache insertion and distributed stop raises. |
| C1 | CODE | [cache factory L15-L40](https://github.com/ml-explore/mlx-lm/blob/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02/mlx_lm/models/cache.py#L15-L40); [KVCache L339-L407](https://github.com/ml-explore/mlx-lm/blob/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02/mlx_lm/models/cache.py#L339-L407); [BatchKVCache.filter L982-L999](https://github.com/ml-explore/mlx-lm/blob/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02/mlx_lm/models/cache.py#L982-L999) | Model-specific cache factory, logical offset versus allocated capacity, and aligned batch padding/offset filtering are distinct contracts. |
| C2 | CODE | [ModelProvider.load L492-L501](https://github.com/ml-explore/mlx-lm/blob/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02/mlx_lm/server.py#L492-L501); [single lookup L1083-L1094](https://github.com/ml-explore/mlx-lm/blob/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02/mlx_lm/server.py#L1083-L1094) | Model key is resolved model/adapter/draft tuple; lookup also uses the token/vision cache key. |
| C3 | CODE | [LRUPromptCache.fetch/insert/trim L1652-L1732](https://github.com/ml-explore/mlx-lm/blob/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02/mlx_lm/models/cache.py#L1652-L1732) | Exact/shorter/longer prefix paths copy cache state; longer-prefix reuse requires trimmability; byte/count constraints evict entries. |
| T1 | TEST-SOURCE | [removal regression L773-L802](https://github.com/ml-explore/mlx-lm/blob/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02/tests/test_generate.py#L773-L802) | Prompt-stage removal keeps currently-processing rows aligned and the survivor generates. |
| T2 | TEST-SOURCE | [test fixture L26-L30](https://github.com/ml-explore/mlx-lm/blob/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02/tests/test_generate.py#L26-L30); [cache fixture L29-L42](https://github.com/ml-explore/mlx-lm/blob/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02/tests/test_prompt_cache.py#L29-L42) | Both test classes load a Hugging Face model; selecting an apparently small method still invokes setup. |
| D1 | CODE | [pyproject dependencies/extras L11-L47](https://github.com/ml-explore/mlx-lm/blob/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02/pyproject.toml#L11-L47); [cache_prompt command L92-L146](https://github.com/ml-explore/mlx-lm/blob/ab7f7048dc341ced2d84b1887eeb17d60b0d1b02/mlx_lm/cache_prompt.py#L92-L146) | MLX backend variants are explicit; cache command loads a model, generates state and writes a cache artifact. |

Not covered: all model classes, full speculative decoding, VLM cache semantics, quantization kernels, distributed serving correctness and training. No model/native test, server, benchmark or device validation is represented by this readset.

## Supporting read depth

These paths retain the same source revision and 2026-10-21 access date. The
metadata inventory records selected evidence without expanding mechanism scope.

| Supporting path | Actual reading depth |
|---|---|
| LICENSE | License text and Apple attribution |
| pyproject.toml | Selected version/dependency/extras metadata, including L11-L47 |
| mlx_lm/cache_prompt.py | L1-L154, CLI model load, cache generation and artifact-write side effects; not executed |
| .github/workflows/pull_request.yml | Selected dependency/test-data and CI test entry; exact additional ranges not recorded, so no full-workflow review or execution claim |

Loader/tokenizer utilities and the remaining cache/model families were not
deeply read. Test-name navigation and dependency inspection do not establish
model, server or backend correctness, or compatibility with a separately
pinned MLX framework.
