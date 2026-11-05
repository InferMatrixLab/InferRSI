# PR9283 cuDNN single-AB performance pilot

Overall INCONCLUSIVE for promotion. Both performance arms completed all seven conditioning and seven measured invocations,256 requests each; measured JIT counts are zero and work/cleanup isolation checks passed. All7168 numeric request rows are retained unchanged. Throughput is PCM frames/s; TTFA is milliseconds and RTF is mean request RTF. No token/audio/text payload is public.

Mixed tradeoff: C1 mean RTF increased about0.36%, C2 about3.26%. At C64 throughput rose about7.79% and RTF fell about6.06%, while TTFA p50 increased about7.12% and p95 about2.02%. Exact all-seven results and signed percentage changes are in paired-matrix.json; this is one ordered AB observation, not isolated causal gain, statistical assurance or service promotion. Endpoint targets remain unmet. New-card quality is excluded here while running; prior other-card quality does not qualify this run.

Actual tested source a83eb6ed38fde8c6964a0315420f52e69706d31c includes PR9283 adapter and measurement/JIT fixes plus opt-in cuDNN preset. Both arms use full streaming2GPU with only codec_cudnn_benchmark changed. Logs/scripts/private identities are hash-only; sampled ownership does not prove continuous isolation between observations. Startup codec timestamps are logged markers, not controlled startup-cost measurements. Original/retained hashes describe distinct representations and do not guarantee private payload availability.

Campaign https://github.com/ThinkFlowLab/OmniRSI/issues/112
Independent privacy/source review required before publication.
