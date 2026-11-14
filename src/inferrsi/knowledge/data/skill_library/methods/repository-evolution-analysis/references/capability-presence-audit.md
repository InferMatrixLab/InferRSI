# Capability presence audit

A procedure for answering one narrow question: **does the claimed capability actually run at this revision, and through what gate?** It is narrower than a capability-family analysis and wider than reading a README.

Use this reference when a release note, README or vendor document lists features and you must state what the code does. Do not use it for performance claims — this classifies presence and wiring, not speed.

## The four buckets

Every claim lands in exactly one:

| Bucket | Test | Typical evidence |
|---|---|---|
| **Implemented** | A reachable call path from the public entrypoint changes behaviour | A caller that is not gated off, plus a body that is not empty |
| **Hook** | A symbol exists and is called, but its body is empty, or its caller is gated off by a value that never occurs | Empty virtual method with no subclass; a body behind a constant-false gate |
| **Documented only** | No symbol, or symbols only in tests and docs | A tree-wide search that returns nothing in the called graph |
| **Contradicted** | The code does something different from the claim | A default that inverts the claim; a backend that asserts instead of degrading |

A claim that fits two buckets is under-specified. Split it before classifying: "asynchronous scheduling is enabled by default" is two claims, one about existence and one about the default.

## Procedure

1. **Record the claim verbatim.** Do not paraphrase into something easier to confirm. Note whether it is a feature list, a hardware list, or an exclusion list. Exclusion lists are the easiest to audit and the most informative: a README that says "does not ship X" is making a falsifiable claim.

2. **Find the entrypoint that would exercise the claim.** Follow from the public entry, not from the directory that shares the claim's name. Name-adjacency is the most common false positive.

3. **Classify.** Use the table above.

4. **For every hook, find the gate.** Ask what would have to be true for the body to run, then check whether that condition can be true in this build. An empty virtual method plus no subclass is a hook. A real body behind a flag whose value is a constant is also a hook. A flag that defaults false is *not* a hook if the documentation says it is optional.

5. **Check for subclasses and registries.** A base class with virtual methods proves nothing. Search for derived types and for registration. Record the command shape, because "no subclass found" is a claim about a search.

6. **Check defaults, not just existence.** A feature can be present and inert. Read the environment-variable or configuration default and quote it. Then check whether some other construction path overrides it — a `setdefault` in a dataclass `__post_init__` can make a variable default-false in one sense and default-true in another.

7. **Separate the four claim strengths.** Exists, is correct, is fast, is end-to-end usable. Never let one imply another.

8. **State the extraction boundary.** Say explicitly whether the tree is complete. Only a complete tree lets "absent" mean absent; a sparse checkout licenses only "not located in the inspected paths".

## Worked instance

Applied to [deepseek-ai/DeepInfer @ 8b16149741a4935e1dec8cea27853f273b374c5b](https://github.com/deepseek-ai/DeepInfer/tree/8b16149741a4935e1dec8cea27853f273b374c5b), by static source reading only. The supplied source-reading archive includes the parent and six direct vendor snapshots, but omits nine listed media files and leaves ten nested vendor gitlinks unexpanded. Its untruncated upstream tree inventory describes the snapshot before those omissions; it does not make the delivered archive a complete checkout or build environment. The observations below are bounded to the named parent-source paths, not an absence proof over omitted or external code.

| Claim (verbatim from README) | Bucket | Deciding evidence |
|---|---|---|
| "Asynchronous scheduling (zero-overhead batch scheduler)" / "Enabled by default." | **Implemented**; constructor-dependent default | [The worker defers decode post-processing](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/worker/worker.py#L182-L187). [EngineArgs uses setdefault and rearms the variable](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/engine/arg_utils.py#L48-L55), with [NORMAL/COMPLETION true and PROMPT false](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/engine/engine_type.py#L15-L17). The standalone [EnvVar.bool default is false](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/environ.py#L69-L71). These construction contexts are not contradictory; an explicit environment value is preserved. |
| "Parallelism: Attention DP / balanced CP, MoE EP + EPLB" — the EPLB rearrangement part | **Implemented**, opt-in; not a Hook | [Model sampling calls the EPLB manager](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/model_executor/models/deepseek.py#L402-L409), which [calls each balancer](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/model_executor/eplb/__init__.py#L378-L384). Its [real update/rearrange path](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/model_executor/eplb/__init__.py#L131-L165) returns when the interval is zero and skips EP size one. The [interval defaults to zero](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/environ.py#L111-L117), using the [integer default](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/environ.py#L62-L63). This disables dynamic rearrangement by default, not the implementation or all load statistics. |
| "A KV cache system" — under the README's complete-service exclusion heading | Service save-integration **Hook**; in-engine KV **Implemented** | [README:38-42](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/README.md#L38-L42) excludes components needed for a complete service. The inspected [save-integration methods have no implementation](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/engine/llm_engine.py#L815-L822); this does not mean device KV is missing: [CacheEngine allocates KV/state storage and constructs GPUCacheInterface](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/worker/cache_engine.py#L918-L966). |
| "VE/Prefill/Decode disaggregation (most required engine functionality is already implemented)" — the same service exclusion list | **Hook** at the inspected integration seam | [init_pd_split](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/engine/llm_engine.py#L800-L809), [send_processed_prompts and post_process_model_outputs](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/engine/llm_engine.py#L848-L858) have no implementation in the base engine. The bounded parent-source search described below located no subclass; this does not negate the README's statement that supporting engine functionality exists. |
| "Load balancing across data-parallel replicas for both prefill and decode" — the same service exclusion list | **Documented only** within this readset | [README:38-42](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/README.md#L38-L42) states the service exclusion. This bounded hook/default audit did not establish an application request router or audit omitted/external implementations; it makes no stronger absence claim. |

Two subtleties the exercise surfaced:

- **`finalize_seq` is not empty.** It is inside the same virtual block but [calls scheduler.free_seq](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/engine/llm_engine.py#L804-L806). So the hook block is heterogeneous: an implementation inheriting it would get partial behaviour rather than nothing. A blanket "all these are empty" statement would be wrong.
- **A body can exist behind an inactive base-class gate.** [do_copy_state](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/engine/llm_engine.py#L787-L798) performs a copy only when its buffer exists, while [should_copy_state returns False](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/engine/llm_engine.py#L811-L813) in the inspected base engine. Body-present alone is not evidence that this entrypoint executes it.

## Pitfalls

- **Name-adjacency.** A directory or class named after the feature is not evidence that the feature runs. In the audited source, three claimed-absent components were present as named empty methods — the name was *more* misleading than absence would have been.
- **Body-present-is-not-reachable.** See the state-copy case above.
- **Flag defaults.** EPLB dynamic rearrangement is opt-in, whereas ZOS is enabled by the standard NORMAL/COMPLETION EngineArgs constructor when no environment override exists. Reading the variable's standalone default alone gives the wrong answer for that entrypoint.
- **Hardware lists.** A supported-device list is not a compatibility guarantee. Check whether unsupported cases assert or degrade silently; in the audited source one property hard-asserted on the non-NVIDIA backend.
- **Documentation that describes the deployment, not the code.** A production Q&A can truthfully describe a shape the open release does not implement. Label it DOC and keep it separate from CODE findings — both statements can be true.
- **Comments as evidence, carefully.** A source comment saying "virtual method, handles finished requests" is the author's description, not the behaviour. Read the body. The same applies in reverse: a comment stating a correctness requirement (as `mtp_varlen.hpp:160` does) is evidence of intent that must then be checked against the code that follows it.
- **Sparse checkouts.** Absence in a curated skill-doc checkout proves nothing. Say so rather than reporting a feature as missing.

## Output

A table with one row per claim: claim verbatim, bucket, deciding evidence, the gate that would enable it, residual uncertainty. Then a short list of findings that change how the release may be described.

## Evidence this instance produced

- The full-SHA path/line links above distinguish feature code, constructor defaults and the complete-service exclusion list; none is native execution evidence.
- Bounded search: `rg --no-ignore -n -F LLMEngine deepinfer tests`, plus class-declaration inspection, at the stated pin. The located declaration is [llm_engine.py:130](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/engine/llm_engine.py#L130); the public entry [constructs that engine through EngineArgs](https://github.com/deepseek-ai/DeepInfer/blob/8b16149741a4935e1dec8cea27853f273b374c5b/deepinfer/entrypoints/llm.py#L77-L84). No subclass was located in those two inspected directories. Vendors, unexpanded gitlinks and external deployment code are outside this search.
