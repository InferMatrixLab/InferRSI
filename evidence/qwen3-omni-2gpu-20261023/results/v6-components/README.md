# Completed v6 component diagnostics

Global status INCONCLUSIVE. No service promotion, quality acceptance or achieved target claim. Only completed codec cuDNN component pair, full17 eager/compiled numerical parity, and exact sampler-math/zero-support research are included. Current service quality pilot and capture experiments are excluded.

Codec is one fresh-process pair on nine bounded shapes with synthetic valid IDs and real checkpoint weights. Preserve all non-bitwise PCM differences; component graph replay speedups are not service speedups. PASS in component reports means their stated execution/shape/finiteness/storage scope only.

Full17 uses real weights and synthetic inputs, with zero/random future-slot modes; eager and compiled results have separate scopes. The copied design describes initial preparation, so its “GPU not performed” sentence is historical and superseded only for the retained eager/compiled result files. No speculative model integration or distribution guarantee follows from causal parity.

Sampler proofs use rational arithmetic; zero-support extension is separate. They do not validate FP32/native RNG or model verification numerics beyond the recorded tests. NVIDIA source is immutable e649dadcbbf049fa4caf2f09f3a3275ca56751db, linked in design; native campaign source4645 is also linked. No foreign measured gain is imported.

Tensor payloads and GPU/harness scripts are hash-only private originals. The two portable CPU sampler-math scripts are included byte-for-byte. Logs are compressed after redaction; original and retained hashes have different identities. All numerical JSON scalar evidence is retained exactly except explicit private process/device identities. Hash integrity does not establish public availability of omitted payloads. Independent privacy and source review completed before publication.

Accepted campaign: https://github.com/ThinkFlowLab/OmniRSI/issues/112

Reproduction: import the portable math prototype and call `check()` to rerun its exact CPU checks without invoking its result writer. The zero-support script also exposes `check()` for the same non-writing workflow. Do not execute a result-writing main entrypoint against retained evidence files or overwrite original results.
