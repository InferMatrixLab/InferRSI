# FlashAttention prefill attempt: bounded service timeout

Refs [Issue67](https://github.com/InferMatrixLab/InferRSI/issues/67).
Head14bd5689892d69721d1020944d295ae61877f1ee against base5738647ba11237a62da40c173998293f6c0a8ca1; model-plane fresh-prefill-only optimization. GPU2113 FAILED124:0 after127allocated single-GPU seconds. The118s HTTP work limit interrupted the second service during startup. Native startup took46.096s; the second arm never reached readiness or made a request. No paired E2E improvement or regression can be inferred.

The actual24Q/4KV/head256 BF16 operator diagnostic completed:129-token comparison NRMSE0.002609077375382185,maxabs0.015625; causal-prefix invariance and8192-token zero-output controls succeeded. No numerical acceptance tolerance was introduced. Native HTTP warmup8192/16 and measurement8192/2048 were valid. Native measured TTFT2.851307050s,TPOT13.407917835ms,total30.297314858s. These one-arm observations are not an improvement claim and cannot substitute for a matched baseline/candidate matrix.

Native process exited0; interrupted FlashAttention service exited-15 after TERM. Both owned groups were empty, no forced kill or cleanup error was recorded. No candidate Graph/task-quality result was obtained. DeepGEMM overlay pre/post hashes were identical. Raw archive SHA2569f2b7953ef53d95ebb2d45f26b8b4a5c4383562e07140aa11a9badc0893b29f6 remains private; curated records retain all failures. Campaign verdict INCONCLUSIVE; PR15 stays draft pending model/E2E evidence.

Preparation negatives are preserved: initial50s cleanup grace omitted possible synchronous postflight signal delay and was corrected to60s before execution. Slurm rounded the requested208s allocation to240s; the submission directive alone was not a208s hard bound. Actual127s remained within authorization, but future sub-minute caps need independently enforced deadlines or whole-minute reservations. Do not retrospectively describe this as a verified208s hard limit.

Readiness is now7119/7200GPU-seconds,81seconds remaining; the separate initial147seconds are unchanged. Baseline4h/search8h/final30h budgets remain unused. Do not squeeze another cold two-service trial into81seconds; qualify/freeze the next appropriate stage. All original preparation and this incomplete attempt remain in KnowledgeStore history.

The parent's first local verification helper rejected a null SSE usage field with AttributeError. The corrected reader explicitly selects non-null usage events; raw evidence and the benchmark observer were unchanged. Both actual native responses and cleanup records were then checked successfully.
