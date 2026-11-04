# Official-client accounting and longer Graph readiness

Governing issue: https://github.com/InferMatrixLab/InferRSI/issues/67.
The harness slice and prospective GPU bounds were declared before execution in
issue comments 6346158087 and 6346252423. This is not an acceptance freeze.

One plane: harness. Source23417bbf13548127fdd0b49dbb26e495a38d9af6 changes only
HTTP protocol handling, socket tests and service documentation from merged
896c9214739b24adeae5c677511877e89e625a99. Model/runner/Graph kernels are unchanged.
The reference is vLLM0.32.0 source5df63a7203cdb9328d824a27b682e77c7b9928be:
completion protocol/serving and benchmarks/lib/endpoint_request_func.py.
The latter installed module must match SHA256
f31fae8c573ecc4bf8e31dae03823502e71404333e8111f4b535432758302b29.

The adapter accepts neutral repetition_penalty/logprobs, ignore_eos, requested
stream usage and first-choice prompt IDs. Normal completion sends finish_reason
on its final token. The upstream client times any nonempty choices list,
including empty-text choices; an extra terminal choice therefore adds a spurious
inter-token interval. Usage-only chunks must have empty choices. The client's
success flag does not validate streamed error objects or terminal reasons.

CPU protocol checks use synthetic real HTTP sockets. The original server must
reject the client's payload without model work; the repaired server must return
one token under natural EOS and four under ignore_eos, actual usage replacing an
intentionally wrong caller prompt-length estimate, and zero/three ITL values.
Version1 failed before requests because it imported a pytest-dependent server
fixture inside the unchanged client environment. Version2 runs that fixture in
the existing test environment and keeps the official client environment intact.
Both source versions and the failed attempt are retained.

The subsequent GPU diagnostic is bounded at one GPU for30minutes, charged to
the remaining1.96GPU-hours in the approved readiness stage. Two sequential
service processes use the same assigned GPU and official FP8 weights: Graph,
then eager; context4096 and concurrency1. Cases783/1/424 use natural EOS/max2048;
case783 then uses ignore_eos/exact1024 to cross the selected1024 Graph capacity.
All8 requests are retained, including differences. No reduced replacement work.

The official unmodified request function uses a transparent response-chunk
recorder. Original wire/client data stay private because model identifiers can
contain local paths. Selected token sequences, hashes, counters and timing are
published. Validate exact input echo, usage/output agreement, ITL count, DONE
and healthy terminal framing, then zero active requests/state. Compare complete
Graph/eager token sequences. Startup/prewarm are separate; fixed arm order,
small scope and response recording preclude a performance or quality PASS.

Bounds: startup180seconds/service, HTTP300seconds/request, command1720seconds,
Slurm1800seconds; owned-process cleanup with20-second graceful deadline.
Preserve Slurm device visibility and task-local paths/caches. No GPU dependency
install or vLLM baseline server is included. Historical full model-byte intake
is reused; a fresh full-shard scan is not claimed.
