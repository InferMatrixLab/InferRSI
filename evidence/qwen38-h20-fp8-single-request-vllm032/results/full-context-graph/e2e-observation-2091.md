# Full-context Graph: actual bounded E2E result

Issue67; execution COMPLETED0:0, one H20 for265 GPU-seconds, released. Formal quality/retrieval/performance acceptance remains INCONCLUSIVE. Readiness usage6740/7200GPU-seconds;460 remain. Initial147 seconds are separately authorized;44GPU-hour phased cap unchanged.

Tested source2061bbcda4bb886fd1bb0468c5f1aa587aaa0300. Final candidate cc651a5bc0696676ff4d214c4a13a7d586a5084c has the exact same tree6a4b128996625a3359ab0d4d9d0e32e112e7417e after merging current main; documentation conflict resolution retains the tested bytes. Both arms use FlashInfer small-M and DeepGEMM prefill with unchanged official FP8 weights/scales, same runtime and pinned official HTTP client. Only the Graph capacity policy differs. Default buckets remain the default; full_context is opt-in and requires one active request.

Before HTTP, one whole-model check used capacity10240 for both eager and Graph, the fixed8192-token input and shared history chosen online from eager argmax. It produced16 predictions including initial prefill and15 Graph replays. Every logit was finite and exactly equal; final live KV through8207 tokens and full convolution/recurrent states were also exactly equal. This is bounded same-model Graph correctness, not an externally frozen history or general task-quality gate.

Each HTTP arm ran one8192/16 warmup followed by one8192/2048 measured request, ignoreEOS, concurrency1. Order: buckets then full_context. All2048 outputtoken IDs match; raw prompt echoes, counts, usage, terminal reason, final DONE, client ITL and timing computations were verified for all four requests.

| Graph policy | TTFT s | TPOT ms | Request s |
| --- | ---: | ---: | ---: |
| Default buckets |3.529094479|52.299018888|110.585186143|
| Full context |3.527905262|16.347277948|36.990783221|

Full-context/control ratios are0.999663025 TTFT,0.312573320 TPOT and0.334500348 request latency. This single-case E2E improvement follows removal of the mid-generation eager transition; it does not establish formal10-input/3-repeat parity or quality. The vLLM observation from2084 belongs to a separate run and is not a same-job baseline for2091.

Actual loader/provenance dtypes are valid. Full-context Python forward counters are1600 total:800 FlashInfer and800 DeepGEMM, representing one graph's warmup/capture plus two prefills, excluding replay. Buckets report721200 total (720400 FlashInfer,800 DeepGEMM), consistent with the later eager decode. No Triton GEMM was selected. These Python counters are not hardware kernel launch counts.

Reported graph-prewarm allocated-memory delta was1821.403MiB for all five default buckets and853.501MiB for one full-context graph. This is neither peak model memory nor a general memory-reduction claim. The configured full context can reserve more per-request KV than a shorter bucket for other workloads.

Both services completed with zero active requests/state, exit0, no observer force-kill, no remaining owned group and no cleanup errors. Overlay pre/post authentication matched all899 files and licenses; imported operator origin was checked. Package and runtime dependencies were unchanged. Startup/JIT/warmup are excluded from timed requests.

Archive SHAb95c6c7a8c8258ec0cb489614c56523519c612b5bcf6d621871b9e3e28e87bc7;27 authenticated payloads plus their hash list. Private raw logs, paths and device identity remain outside the repository. The initial CPU-review lazy-capture boundary defect and fix are retained in the preparation case;23 CPU runner tests passed. Independent actual review verified all source/result hashes, four SSE/client records, exact Graph states, operator origins and cleanup; no remaining blocker. PR13 merged at77f4ab13ddce1b4b0ba6f1ae5e612608959fbd1b from reviewed headcc651a5bc0696676ff4d214c4a13a7d586a5084c against base83d82067e72f500fd81163fc7ccfda979a499200. Current-head Actions/status lists were empty. This opt-in integration does not close Issue67 or establish formal parity.
