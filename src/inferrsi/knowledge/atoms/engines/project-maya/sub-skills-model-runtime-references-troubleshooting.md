# Runtime-planning diagnosis

Use one discriminator at a time. Preserve the failing representation and its
identity; do not regenerate packs, edit deployment configuration, download
models or launch setup merely to make a symptom disappear. Read
[model and memory](model-and-memory.md) for the bundled contracts.

| Symptom | Invariant and smallest falsifier | Recovery / stop condition |
| --- | --- | --- |
| A `maya` executable is assumed to mean GLM, or `--pack` is assumed to mean DeepSeek | Qwen uses the same executable and also writes `--pack`. Check the installer family, executable basename and valued `--ple-gguf` together; the bundled helper screens this projection without launching it | Preserve the original config, establish the actual checkpoint/pack family, and correct only an authorized projection or deployment. Stop on contradictory explicit identities; fallback-to-GLM is not compatibility evidence |
| Two `Maya-S` files have similar size/bits but a pack fails to load | Tier names and bit counts do not encode tensor/slot ABI. Compare family, format, geometry, role types, codebooks and actual byte ranges | Keep family-specific packs and bytes together. Never rename `mm3.txt` to `ds4.txt`, flatten EXL3 into affine Q4, or bypass shape/type errors. Actual payload unavailable means compatibility remains unknown |
| GLM reports a native-expert row disagrees with its shard directory | Each role needs its own shard, type and absolute offset. A different shard's data start is a concrete counterexample even when file sizes agree | Retain the discrepancy and hashes. An authorized trusted family-specific repack may be needed; this skill does not bundle a model converter or authorize its side effects |
| GLM rejects shared indexer / k-pool / MLA / mHC geometry, or MiniMax reports geometry not covered | A model-specific kernel guard is part of correctness, not a cosmetic metadata restriction | Compare the relevant bundled geometry checks. Do not "fix" metadata to fit kernels without matching weights and independent native parity. Unsupported geometry stops the route |
| An APU plan appears to fit only after adding GPU aperture to available RAM | Device allocation and pinned host tiers share physical RAM. Sum the unique simultaneous allocations against one audited physical pool | Use `kind: unified` in the helper. Separate Windows commit from physical availability. If available RAM/commit cannot be established, stop rather than treating aperture or page-file size as extra physical memory |
| `--expert-cache 3000` is interpreted as bytes, per-layer residency or a universal flag | GLM caps the first part by 3000 largest expert slots; actual per-layer main/spare/tail slots determine residency | Obtain the measured slot strides and effective pool assignment; keep later parts and reserve separate. Do not copy a GLM slot number into MiniMax staging or saved-conversation settings |
| Automatic memory planning succeeds on paper but allocation fails or the machine pages | Estimates may omit lazy MMQ scratch, touched allocations, graphs, snapshots, pinned staging, other processes or commit charges | Compare planned versus effective unique allocations and reserve at the same boundary. Reduce authorized context/concurrency/chunk/pool, one variable at a time. A budgeting floor is not proof the driver can allocate it |
| More conversations unexpectedly reduce expert residency or context | GLM adds private arenas/snapshots before pool sizing. MiniMax parallel operation uses private VRAM KV and disables streaming/DSpark | Rebuild the peak ledger with the actual sequence count and effective settings. Do not multiply a streamed single-request plan or count shared weights once per session |
| A zero-valued GLM environment knob is assumed enabled merely because it exists | The inspected GLM memory helper parses numeric values with `atoi != 0`; other knobs can differ | Record the exact knob and parsed semantics; do not generalize one engine's or another knob's presence rule. Retain malformed/unknown settings rather than guessing |
| CMake's version/comment contradicts the checkout, or a synthetic test prints tok/s | Source release is `VERSION=1.1.34`; historical build constants/comments and modeled output are different evidence classes | Record source/build/toolchain identities separately. Treat modeled rates as simulation output, never measured decode throughput |
| No GPU/toolkit/weights, but four direct C++ tests are green | Those tests cover pure policy/simulation/retention functions, not native inference or all production callers | Keep `BLOCKED_REQUIRED_BACKEND` and absent assets explicit. Require the corresponding native backend/model evidence before qualification; do not add a CPU backend claim |
| Qwen is offered but its deep implementation was not inspected, or `--parallel` is requested | Qwen has a distinct GGUF/n-gram route and is excluded from the launcher's parallel family list | Route the shallow format/hardware/licensing checks here, mark deep-kernel/native gaps, and refuse inferred multi-request decoding support |

## Escalate rather than silently broaden execution

The setup wrapper can create or delete a private environment; its installer can
download, compile, pack, calibrate, pin RAM and start a server. Even a nominal
help invocation through that wrapper can mutate the environment before Python
parses the request. Default CMake native-experts configuration can fetch pinned
llama.cpp. These are not read-only diagnostics. Obtain the separately required
execution authority and resources, or leave the result blocked.

The offline helper reads one bounded JSON planning file and prints JSON. It has
no network, subprocess, engine import or configuration-write path. Its rejected
plan is a useful cheap falsifier; its accepted arithmetic is not a correctness,
licensing, resource-fit, quality or performance certification.
