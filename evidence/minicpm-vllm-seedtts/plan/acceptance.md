## Outcome and user need

Optimize MiniCPM-o 4.5 turn-mode streaming voice cloning in vLLM-Omni for users needing lower waiting time and higher single-GPU concurrency. The user explicitly approved profiling Code2Wav, batching and inter-stage scheduling, implementing measured improvements in one vLLM-Omni PR, and contributing the evidence and reusable lessons to InferRSI.

## Fixed comparison

- Hardware: one exclusively allocated NVIDIA L20X per comparison, with private MPS; sequential engines on the same physical device.
- Initial vLLM-Omni revision: d111310d548486118a2d22a943fa0a10fcff65e2. An unrelated local duplex modification is excluded from the contribution.
- Independent engine revision: b6a6cb16f68fba336170e1600067af4f1a5eb5c4, profile `track_s_fast_r16`.
- InferRSI runtime: a590ccb25596396a592f237105166ade4aedeaaa.
- Model: openbmb/MiniCPM-o-4_5 revision 503e754207c94da6bb26850b4469f367c9ea3582.
- Workload: Seed-TTS-eval English voice cloning, dataset revision 8f5e1aa2a35d42f42e940074c1983358b9491f89. Reuse the independent engine's canonical requests, disjoint warmup/tuning/evaluation pools, sampling parameters and client metric implementation.
- Required concurrency: 1, 16, 32. RTF is the unweighted mean of per-request (last unique audio arrival minus dispatch) / delivered audio duration. Report each concurrency separately.

## Acceptance and evidence

The user's performance gate is strictly lower mean RTF than the independent engine at all three concurrencies, with no speech-quality regression. Historical published engine numbers are references, not a substitute for a matched local comparison.

Use tuning requests for development only. Final evaluation uses 320 requests at C1/C16 and 640 at C32, 2*C warmup requests, a discarded initial run and five measured fresh-server runs. Preserve failures, per-request timings and generated audio. Compare identical request and sampling inputs. Report repetitions and variance; a missing cell or unresolved measurement/quality evidence remains INCONCLUSIVE.

Retain exact-stage parity tests for lossless changes. Validate end-to-end speech with WER, speaker similarity and UTMOS against the frozen unmodified vLLM-Omni reference; do not approve approximations based only on speed or numerical kernel tests. No quality tolerance relaxation is authorized by this campaign. Any unresolved quality comparison prevents a PASS claim.

Implementation candidates and final validation must retain source/configuration identities. Keep development screens distinct from qualification. Submit only evidenced improvements, with limitations and unsuccessful hypotheses documented. PR readiness and campaign success are separate decisions.
