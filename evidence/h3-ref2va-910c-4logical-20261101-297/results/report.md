# MiniMax-H3 Ref2VA on four logical Ascend 910C devices

Evidence cutoff: 2026-11-02 15:52 +08. Governing acceptance: [#297](https://github.com/InferMatrixLab/InferRSI/issues/297).
**Campaign verdict: INCONCLUSIVE. No accepted 50% complete-HTTP latency reduction.**
This is a tracking snapshot of completed, failed and incomplete work.

## Workload and identities

| Item | Tested scope |
| --- | --- |
| Hardware | Four logical 910C devices, two dual-die physical NPUs, 64 GiB per logical device |
| Model | Original MiniMax-H3 Ref2VA snapshot `6818f6c32d12b210915e44ad56a4228c2608f160` |
| Inputs | 1344×768, 24 FPS, 124/362 frames for 5/15 s, 50 solver steps |
| Reference | Original BF16 dense B0 `df1c1b05936381dbaa3891c1ae4c4b21ab375a5d` |
| Migration source | vLLM-Omni snapshot `922f1e9f1cb85b9f2b66d86e1eb500e6872b2dcb`; separate from original B0 |
| Execution harness | InferRSI `50c19da43e0b358e6f990c00719891ad308a8ac1` |
| Stack | Private Ubuntu 22.04 namespace, GLIBC 2.35, CANN 9.1, Torch 2.10.0+cpu, TorchNPU 2.10.0.post4, MindIE-SD 3.1.0, Cache-DiT 1.5.0 |
| Parallelism | USP4/ring1, TE TP4, tiled VAE parallel4, DLO enabled in the reference; exceptions recorded per candidate |
| Quality | Frozen strict bit-exact contract and automatic lossy gates; no human media inspection |

The MindIE wheel's source revision is UNKNOWN. Model bytes were SHA/LFS checked
privately; weights, input image, raw media, tensors and host logs are external.
This campaign is separate from the eight-device 910B1 evidence in
[PR #294](https://github.com/InferMatrixLab/InferRSI/pull/294). Its results do not transfer here.

## Four-track target status

| Track | Numerical or model-quality evidence | Clean complete-HTTP evidence | Target status |
| --- | --- | --- | --- |
| 5 s lossless | C1 direct-B0 strict comparison: 439 PASS, zero failures/missing; C13 also 439 PASS on the fixed request | One C1 fresh-server screening pair: 291.247763→286.666760 s, 1.572888689% reduction | Performance FAIL at the 50% gate; final confirmation incomplete |
| 15 s lossless | C1 direct-B0 strict comparison: 439 PASS, zero failures/missing on the fixed request | Not run | INCONCLUSIVE |
| 5 s lossy | Tested fast profiles have observed frozen quality failures; no selected complete quality cohort | No qualified candidate's clean pair | INCONCLUSIVE overall; rejected configurations remain FAIL |
| 15 s lossy | Tested Taylor/C11 configurations have independent visual/audio failures at this duration | No qualified candidate's clean pair | INCONCLUSIVE overall; rejected configurations remain FAIL |

Strict qualification covers fixed requests, not a universal bit-exact guarantee.
The original B0 repeated exactly under the contract at each duration (219 checks
each). The default dense migration's 15 s qualification is separate and incomplete.

## Clean screening and timing boundaries

[C1 clean screening](c1-clean-5s-screening.json) used one fresh server per arm,
two same-shape warmups and three measured complete MP4 responses. Audit and
profiling were disabled. Source integrity, cleanup and measured RGB24/PCM checks
passed; the paired strict check had 35 PASS, with the separate audit's 439 PASS.

The measured delta compares original B0 with migration+C1. There is no isolated
migration-only clean arm. Only one screening pair completed; statistical
significance and final acceptance are not claimed. The frozen final protocol
requires three fresh pairs in AB/BA/AB order for each track/duration, two warmups
and three measurements per service, and at least 50% reduction in every pair
and the aggregate. No final-confirmation pair completed.

Audited request times below use zero warmups and one request unless stated.
They are diagnostic observations, not accepted speedups against this clean B0.

## Direction ledger

This index summarizes carried device evidence and points to the published
projections. Full private executor archives remain external. A native-test PASS
or primitive-gate PASS does not establish model quality or service performance.

| Direction | Mechanism and origin | Observed disposition |
| --- | --- | --- |
| C0 | Pinned migration and profiling | Fixed 5 s strict PASS; a two-step trace attributed 7148.150 of 11332.154 ms to FA union. This is not the full HTTP fraction. Raw trace is external. |
| C1 | H3-owned BF16 attention layout and valid-KV prefix | Fixed 5/15 s strict PASS; clean 5 s reduction 1.5729%, below target. Query-fold variants preserved fixture bits but were slower. |
| C2 | HSDP2/replicate2 topology | Four-step bit-exact smoke; cold request about 85.649 s. No complete 50-step performance qualification. |
| C3 | Cache-DiT Taylor2/Taylor3 profiles | Frozen audio or visual gates failed across independent samples/durations; a first passing clip did not qualify a profile. |
| C4 | Native dense FAS/FIA/FIA2 alternatives | FIA2 fixture improvement about 5.4%/5.0% at 5/15 s, non-bit-exact; PFA and query/layout alternatives failed their useful-gain tests. |
| C5 | MindIE Laser for video queries, BF16 conditioning queries | Complete 5 s diagnostic 279.751 s; frozen audio-caption adherence failed. |
| C6 | Laser input-range scaling | Tested scales did not materially improve about 0.002713 relative L2; stopped. |
| C7 | Native RainFusion BF16 | Actual leaf execution observed; fixed sparsity profiles failed frozen quality checks. |
| C8 | Reference-KV device residency and refresh2 | Complete request failed CLAP; creation alone did not prove reuse counts in the older diagnostic. |
| C9 | TP4 with resident DiT | Complete 5 s diagnostic 327.206 s; audio-caption adherence failed. An earlier offload attempt failed before step0. |
| C10 | Local audio modality-veto guard | Native 15 PASS; independent 5 s clips exposed different audio failures. Fixed variants rejected. |
| C11 | Local dual-sigma residual forecasting, including FP32 anchors | Native original 20/FP32 revision 23 PASS. Fixed 5 s and independent 15 s profiles failed frozen quality guards. |
| C12 | Local state-aligned residual prediction | Native 14 PASS; full 5 s executed 50 computes/zero predictions/45 vetoes. No acceleration; cohort incomplete. |
| C13 | Adapted upstream vLLM-Omni PR #9351 ordering to current chunked DLO, over C1 | Focused 10 PASS; expanded309 PASS/1 FAIL, reproduced on the migration baseline. Full 5 s strict 439 PASS; clean timing and 15 s incomplete. |
| C14 | Quantized-attention prerequisites on the actual A3 stack | Block-FP8 and block-INT8 probes failed before FIA2. Per-token INT8 and other SDKs are not disproved. |
| C15 | Local target-video block-residual cache, FP16 storage | Corrected native17 PASS; complete-path attempt failed finite video velocity at first reuse. |
| C16 | FP32 storage repair for C15 | Native 18 PASS; complete 5 s input 134 PASS, but three frozen audio checks failed. |
| C17 | Local three-latent-frame attention window | Native 15 PASS; real-input operation 63.7004% lower. Full-model quality failed 11 checks. |
| C18 | Current-frame detail plus global 3×3 pooled KV | Native 17 PASS; operation 7.2512% lower, below the fixed 50% primitive gate. No full model. |
| C19 | Shared global 3×3 pooled KV | Native 17 PASS; operation 52.8479% lower, but relative L2 0.258805 exceeded the fixed 0.258052 bound. No full model. |
| C20 | C19 plus isotropic key-variance correction | Native 17 PASS; operation 48.4204% lower and relative L2 0.263361; both primitive gates failed. No full model. |
| C21 | Local pre-gate video activation cache | Native 36 PASS; full 5 s diagnostic 163.806 s, input 134 PASS; seven frozen quality failures. |
| C22 | Local sigma-secant pre-gate cache, BF16 anchor/INT8 per-channel delta | Native 45 PASS; full 5 s diagnostic 166.859 s, input 134 PASS; nine frozen quality failures. |
| C23 | Local fresh conditioning attention with cached video-to-video output/LSE | V2 native 44 PASS, static attention cycle 66.4588% lower; full 5 s diagnostic 199.065 s, input 134 PASS; eight frozen quality failures. |

Primary result indexes: [automatic quality comparisons](automatic-quality-checkpoint.json),
[C12–C23 run projections](c12-through-c23-execution-checkpoint.json),
[C1 query folding](c1-queryfold-operator.json), [C4 PFA](c4-pfa-operator.json),
[C11 15 s audit](c11-fp32-15s-00-audit.json), and
[source identities and patches](../patch/README.md).
The ledger summarizes 24 direction families, not 24 successful candidates.

## C23: primitive improvement rejected by full-model quality

Private engine commit `6eb7bb094effb40853431208d1631effaf452a3f` retains all
50 solver steps, fresh QKV/SP/projections/FFN/current gates and original weights.
Each step refreshes nonvideo-to-full and video-to-conditioning attention.
Only video-to-video BF16 attention output and FP32 LSE are reused between full
steps 0,1,4,9,19,29,39,49. This is an intentional approximation for changing Q/KV.

The first manual Triton merge passed 44 native tests but the full 50-call static
attention cycle improved only 38.2552%, below the prospective 50% gate. Component
diagnosis measured 22.750201 ms for that merge and 2.742732 ms for a native Torch
expression, with all 66,834,432 real BF16 output elements bit-equal. V1 failures
and source hashes are retained in the run projection.

V2 adopted that measured Torch expression, keeping the algorithm and gates fixed.
It passed 44 focused tests, including three executed four-rank suites. On one
captured real 5 s input, 50 attention calls with 8 refresh/42 reuse, 2 warm cycles and
5 measured cycles in AB/BA/AB/BA/AB order, cycle medians were 3477.472871 and
1166.387435 ms: 66.458762% lower. All 50 validation outputs were finite, max relative
L2 was 0.00201662234 < 0.005, and saved real-merge replay was bit-equal to V1.
This excludes FFN, changing inputs, complete-model timing and HTTP.

[Full 5s-00 execution](c23-5s-00-execution-proof.json) then completed all 50 steps
with 134 input checks and expected per-rank counters: 400 context refreshes,
2100 reuses, 2500 fresh conditioning-attention calls and 2500 full-row FFN blocks.
Persistent cache peaked at 6787872000 bytes/rank and closed to zero live bytes.
Diagnostic complete HTTP was 199064.918509 ms. The frozen scorer rejected 8 of 39
checks: DINO/CLIP/CLAP similarity, segmented CLAP, reference-DINO adherence,
audio-caption adherence, audio level and audio envelope. The other 9 missing
samples do not erase these violations. No 15 s or clean timing extension follows.

## Limits and continuation

All 24 direction families are charged. The requester extended the original budget
to 32 wall hours/128 logical-device-hours, ending 2026-11-03 01:19+08; preparation,
failures and retries remain charged. The controller-alias repair groups two
duplicate labels under their existing source-bound families, preserving the
raw budget and failed attempts: [audit receipt](c21-c22-direction-identity-correction.json).
No additional final-confirmation budget is authorized.

[Retirement readback](c23-retired-proof.json) verified selected devices idle,
experiment ports free and tested source/helpers/validators unchanged at
2026-11-02 15:48:59+08. No device job is scheduled by this tracking PR.
Further mechanism search requires a requester extension beyond 24 directions.
Four-track final confirmation, full lossy corpus coverage and independent review
remain incomplete. Goal acceptance belongs to the requester.

Published files are sanitized field projections and patch snapshots. They do
not contain model/scorer weights, media, raw tensors, full executor archives or
the private namespace/bootstrap environment. [Replay and availability notes](../plan/reproduction.md)
describe what can be verified locally and what still needs external artifacts.
