# Pinned llama.cpp runtime-state contracts

Repository: [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp/tree/707616feb5f379e99ff7442680a55b4a1704c7c9). Revision: `707616feb5f379e99ff7442680a55b4a1704c7c9`. Root [license](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/LICENSE#L1-L21): MIT, The ggml authors. Third-party notices remain independently owned upstream. Inspection date: 2026-10-21.

Evidence classes: **CODE** means an inspected implementation/public contract, **TEST-SOURCE** an inspected but unexecuted test assertion, **HYPOTHESIS** a proposed diagnostic or verification transfer. No native test, benchmark, model-quality comparison or AREX/DisCo runtime evaluation was performed for these contracts.

## S1 — Memory planning and execution have different owners

**CODE**: [`llama_init_from_model`](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/src/llama-context.cpp#L4021-L4125) checks context/model compatibility before constructing a context. The context creates its memory through [`model.create_memory`](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/src/llama-context.cpp#L474-L484); the model-specific implementation is not a universal paged-KV owner.

[`llama_memory_i::init_batch`](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/src/llama-memory.h#L44-L127) plans ubatches and the state needed to process them; `llama_memory_context_i::apply` applies the current ubatch's memory state. The decoder runs pending memory updates, obtains the batch plan and handles its status before execution ([decode preparation](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/src/llama-context.cpp#L1879-L1971)). [`process_ubatch`](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/src/llama-context.cpp#L1507-L1579) applies memory before graph/input processing.

Implication: logical batch size, ubatch size, allocated memory, successfully computed positions and caller-visible token accounting are distinct. The interface describes KV as one kind of LLM memory; recurrent/hybrid behavior needs its own contract.

## S2 — Abort/fatal decode errors can retain completed ubatches

**CODE**: the [public decode contract](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/include/llama.h#L994-L1008) distinguishes 0 success, 1 no KV slot, 2 abort, -1 invalid batch and less than -1 fatal error. For abort/fatal errors, processed ubatches remain in context memory; the caller is directed to query sequence position min/max.

The [failure path](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/src/llama-context.cpp#L1981-L2031) derives per-sequence minimum positions from the failed ubatch, removes memory entries from those positions onward, and translates the graph status to 2/-2/-3. This is not whole-logical-batch transactional rollback. The readset does not establish every memory implementation's conformance under injected failures.

**HYPOTHESIS**: a recovery audit should compare caller progress against observed per-sequence memory ranges and the concrete memory removal result before retrying. An injected-abort test must show at least one earlier ubatch completed and inspect retained state; merely receiving return code 2 is insufficient.

## S3 — Sequence state operations are model-scoped

**CODE**: the memory interface exposes removal/copy/shift and state read/write operations ([interface](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/src/llama-memory.h#L108-L127)). A Boolean removal result is a capability/result to inspect, not permission to assume arbitrary rollback. The [public sequence position queries](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/include/llama.h#L804-L820) expose actual ranges rather than caller counters.

**TEST-SOURCE**: the [KV sequence-isolation case](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/tests/llama-context/cases-kv.cpp#L72-L117) decodes two sequences, removes one and requires the other's serialized state to remain byte-identical. [State replay](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/tests/llama-context/cases-kv.cpp#L121-L152) compares continuation against the baseline using the native test's numerical criterion.

The [recurrent rollback implementation](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/src/llama-memory-recurrent.cpp#L189-L219) rejects partial rollback of shared cells, bounds it by `n_rs_seq` and treats a pending rollback as single-use. The [recurrent rollback case](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/tests/llama-context/cases-rs.cpp#L163-L195) requires rollback capacity and can skip. Its [replay section](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/tests/llama-context/cases-rs.cpp#L211-L267) checks exact logits for same-configuration replay and leaves a second partial-rollback block commented as invalid under the stated condition. Do not generalize this to unlimited repeated recurrent rollback or call a skip a pass.

## G1 — Reuse requires topology compatibility and valid inputs

**CODE**: [`llm_graph_params::allow_reuse`](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/src/llama-graph.h#L836-L908) checks batch shape/sequence properties, input representation, participating sequence IDs when applicable, output count, sampler identity and output routing, nextn offset, selected context flags, architecture/graph type and adapter/cross-state pointer identity. This is an inspected predicate, not a claim every possible topology parameter is proven complete.

[`llm_graph_result::can_reuse`](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/src/llama-graph.cpp#L1478-L1507) also requires all input-specific reuse checks. For example, [`llm_graph_input_attn_kv::can_reuse`](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/src/llama-graph.cpp#L563-L575) rebinds the memory context and checks input/mask compatibility; its V-index check is explicitly commented out. The other model-specific input implementations were not all audited.

[`process_ubatch`](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/src/llama-context.cpp#L1514-L1574) additionally requires enabled reuse and the previous active result. A miss resets scheduler/result, builds and allocates; a hit retains the graph, but both paths set fresh inputs. In pipeline-parallel mode it synchronizes before those reused input tensors can be overwritten. The context owns [two previous-result arenas selected by output presence](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/src/llama-context.h#L414-L429).

**HYPOTHESIS**: when a graph miss is surprising, compare all relevant predicate inputs and the active result, not just token count. This frontend graph reuse is a separate layer from backend-native captured-graph eligibility/cache behavior. No captured graph hit, allocation saving or speedup is established here.

## G2 — Backend submission retains copy/event obligations

**CODE**: [`graph_compute`](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/src/llama-context.cpp#L2731-L2759) selects generation/batch thread settings and dispatches to the backend scheduler. [`ggml_backend_sched_alloc_graph`](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/ggml/src/ggml-backend.cpp#L2093-L2143) advances copy indices, splits/allocates the graph and tracks allocation; async compute calls compute_splits, whereas the synchronous wrapper also synchronizes.

[`ggml_backend_sched_copy_input`](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/ggml/src/ggml-backend.cpp#L1823-L1862) immediately copies user inputs after waiting for the destination copy's use to finish. Other inputs use event waits or backend synchronization and attempt backend-specific asynchronous copy, falling back to synchronized copy if it is unavailable. These are explicit upstream paths, not a proposed fallback layer.

[`compute_splits`](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/ggml/src/ggml-backend.cpp#L1865-L1946) respects reused-buffer ordering across backends, copies non-host inputs before host weights, submits the split and records completion events. Eval callbacks can add synchronization. No actual backend execution, transfer overlap, memory saving or kernel performance is measured by reading this code.

## C1 — Reader cancellation removes logical work through task IDs

**CODE**: [`server_response_reader`](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/tools/server/server-queue.h#L203-L243) owns a set of task IDs and calls stop on destruction. [`next`](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/tools/server/server-queue.cpp#L550-L620) consults should_stop when its receive times out; stop unregisters waiters and posts cancel tasks at the front when work remains.

Posting a cancellation [cleans pending tasks under the queue mutex](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/tools/server/server-queue.cpp#L28-L72). [`cleanup_pending_task`](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/tools/server/server-queue.cpp#L368-L382) covers main, deferred and yielded-unhandled queues. The [normal cancellation branch](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/tools/server/server-context.cpp#L2901-L2910) releases the slot whose task matches `id_target`.

## C2 — Yielding, release and physical interruption differ

**CODE**: [`yield_to_queue`](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/tools/server/server-queue.cpp#L222-L275) keeps compute on the current thread and lets a worker offer tasks; declined tasks return to the main queue in order. The server's [process_single_task gate](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/tools/server/server-context.cpp#L2821-L2843) accepts only metrics and slot-read tasks while yielding. Cancellation is therefore not evidence of immediate compute preemption.

[`server_slot::release`](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/tools/server/server-context.cpp#L586-L607) makes the slot idle, clears child/stateless prompts, invokes reset/release callbacks and resets task state. A normal stateful prompt can remain for reuse. Explicit [`prompt_clear`](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/tools/server/server-context.cpp#L343-L348) removes its sequence and prompt metadata. Retained state alone is not a leak.

The [public abort-callback comment](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/include/llama.h#L401-L405) says CPU execution only. [`set_abort_callback`](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/src/llama-context.cpp#L1306-L1320) installs it only for backend registries exposing the setter. This does not establish arbitrary accelerator preemption.

## C3 — Server fatal-error recovery is deliberately coarse at this pin

**CODE**: server [`decode`](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/tools/server/server-context.cpp#L4284-L4341) calls `llama_process(DECODE)` inside yield_to_queue, synchronizing when successful and output is needed. For fatal/invalid/context-exhausted errors it releases processing slots and clears their prompts, then throws. The source notes that exact partial progress is difficult to track; position reconciliation and return-code-2 abort handling remain TODOs. Nonfatal memory pressure follows the existing retry/idle-clear branch. This readset identifies that boundary, not a proven bug or a qualified fix.

## T1–T3 — Inspected native assertions and limits

- **T1 / TEST-SOURCE**: [tests/CMakeLists](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/tests/CMakeLists.txt#L169-L252) registers a C++ generated-model fixture and context state tests. The internal-symbol cases are guarded out for Windows shared builds. Generated test models exercise implementation structure, not real-model quality; the generator [explicitly skips some architectures](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/tests/test-llama-archs.cpp#L910-L939).
- **T2 / TEST-SOURCE**: [`test_cancel_request`](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/tools/server/tests/unit/test_completion.py#L634-L651) times out a request and checks that the slot becomes idle. It does not assert immediate device abortion, all prompt memory freed, late-output correctness or a cancellation latency SLA.
- **T3 / TEST-SOURCE**: [backend-op selection](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/tests/test-backend-ops.cpp#L13118-L13141) supports selecting backend and operations. Such tests need the actual selected native backend; a CPU result cannot certify accelerator copy/event or captured-graph behavior. The CANN workflow's [listed build job is disabled](https://github.com/ggml-org/llama.cpp/blob/707616feb5f379e99ff7442680a55b4a1704c7c9/.github/workflows/build-cann.yml#L40-L56).

The distributed reading snapshot omitted vocabulary GGUF/media fixtures. This is not evidence those files or capabilities are absent upstream. Do not run a complete upstream label set against that snapshot without restoring its exact required fixtures.

## Readset and intentional gaps

Inspected code: `include/llama.h` decode/abort/memory APIs; context construction, decode preparation/failure, process_ubatch, graph_compute, source wrappers and owned graph/scheduler fields; memory interface; graph reuse predicate/result/one attention input; backend scheduler input-copy/split-compute/allocation; server task/reader/queue/yield/cancel/release/decode paths. Inspected tests: KV isolation/state replay, recurrent rollback limitations, generated-model registration/generator filters, cancellation, backend-op CLI selection. CI/license files were read for validation and attribution boundaries.

Not reviewed as complete implementations: all model builders and memory variants, all input-specific reuse checks, CUDA/Metal/CANN graph caches/kernels, multimodal state, speculative draft-state lifecycle, prompt-cache matching/checkpoint serialization, RPC/network behavior, conversion and quantization quality. No whole-repo audit or runtime conformance is implied.
