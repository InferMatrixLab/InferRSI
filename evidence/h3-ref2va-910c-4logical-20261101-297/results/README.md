# Results status

Campaign verdict: **INCONCLUSIVE**. No accepted complete-HTTP gain exists.

- [C1 strict 5 s comparison](c1-5s-strict-comparison.json): 439 checks pass,
  zero failures/missing, two complete 50-step requests compared with the original
  B0; selected video/audio latent bits, schedule and every decoded RGB24/PCM sample.
  This qualifies this fixed 5 s request, not performance.
- [C1 strict 15 s comparison](c1-15s-strict-comparison.json): 439 checks pass,
  zero failures/missing, two complete 50-step requests compared directly with
  original B0. [Execution projection](c1-15s-execution.json) records actual
  prefix-attention calls: 2,500 per rank per request. Its HTTP values are audited
  diagnostics, not clean performance qualification.
- [Automatic quality checkpoint](automatic-quality-checkpoint.json): observed
  cache, Laser and RainFusion failures are retained with missing sample coverage.
  In particular, the Taylor2 .08/max3 profile failed both 15s-00 and 5s-01 despite
  its first 5s-00 observed gates passing. No human output checks were used.
- [Query-folding operator study](c1-queryfold-operator.json): 2/4/8 query tiles
  remain bit-exact on one real 5 s fixture but are slower by approximately
  2.0%/2.4%/5.2%, including repeated K/V and output-layout restoration. Do not integrate.

- Original C10 Fn1/Bn1 failed 5s-00 CLAP and audio adherence. Its Bn0
  variant passed the first clip's observed checks but failed independent 5s-01
  CLAP. Both variants are rejected for 5 s; 15 s remains independently untested.
- Taylor3 Fn1/Bn1 failed 5s-01 CLAP and a CLAP segment. Diagnostic HTTP
  176.088 s does not qualify this rejected configuration.
- [C11 native execution](c11-native-execution.json): 20 tests passed, including
  two executed Ascend tests covering two-clock forecasting and the actual
  Cache-DiT wrapper's compute/forecast path. Source and cleanup checks passed.
  The private five-file patch is bound to 61b8efa. Both Fn1/Bn0 and Fn1/Bn1
  failed different frozen 5s-00 audio guards; neither is promoted.
- [FP32 residual native revision](c11-fp32-native-execution.json): 23 tests
  passed, including three executed NPU tests. Two test-reference failures are
  retained. Production bytes stayed unchanged across those native attempts.
  The new private patch is bound to d4d25b4. It failed5s-00 adherence
  and five independent15s-00 visual/audio guards; neither duration is promoted.
  [5s audit](c11-fp32-5s-00-audit.json) and
  [15s audit](c11-fp32-15s-00-audit.json) retain actual counts and violations.

Original private executor receipts, native inventory and raw captures remain
outside the repository. These files are selected field projections, not complete
portable trial archives.

- [First clean 5 s AB screening](c1-clean-5s-screening.json): original B0
  median291.247763 s, migration+C1 median286.666760 s;1.572888689% reduction.
  Native performance FAIL at the unchanged50% bar; strict pair quality PASS35
  with separate audit PASS439; source integrity and cleanup passed. One fresh
  pair, two warmups plus three measured requests per arm; no significance or
  final acceptance claim. The delta includes migration+C1, without an isolated
  migration-only timing arm.

15 s clean timing, final three-pair confirmation, full lossy quality coverage
and all four final track decisions remain outstanding.

## Earlier C12–C17 execution checkpoint

[Earlier projection](c12-through-c17-execution-checkpoint.json) retains failures
and actual counters. C13 direct-B0 strict5s comparison PASS439; clean performance
and15s remain unqualified. C14 block-FP8/INT8 probes failed before FIA2; public
MindIE dev already has quant_attention, while the installed3.1.0 wheel lacks it.
C15 FP16 residual failed finite velocity. [C16 actual model proof](c16-5s-00-execution-proof.json)
shows finite full50steps and134input checks but three audio quality failures.
C17 passed15native tests and a real5s operator gate:69.603→25.266ms,63.7004%
reduction, intentionally nonbit output. Its full model failed11frozen quality checks.
No newly accepted complete-HTTP gain exists. All four final tracks remain open.

## Earlier checkpoint through C20

[Earlier C12–C20 projection](c12-through-c20-execution-checkpoint.json) and
[C17 model proof](c17-5s-00-execution-proof.json) retain the completed failures.
C18/C19/C20 each passed17native tests, then failed the prospective operator
screen:7.25%/52.85%/48.42%operation reduction,relL2 .218013/.258805/.263361.
The unchanged primitive bounds require>=50%and relL2<.258052; no full models
were run for these three. All source branches and bundles are preserved.
At that checkpoint selected devices/ports were idle and 21/24 directions were
charged. Runtime diagnostic remains v17. No accepted complete-HTTP gain exists.

## Current checkpoint through C23

[Current C12–C23 projection](c12-through-c23-execution-checkpoint.json) retains
the source-bound native, operator and full-model attempts. C21 passed 36 native
tests but failed seven frozen quality checks on its complete 5s-00 request.
C22 passed 45 native tests but failed nine frozen quality checks. Neither fixed
profile proceeds to 15 s or clean timing. The audited controller-alias repair
preserves the raw budget snapshot, failed attempts and all time charges.

C23 V1 passed 44 native tests but reduced its static real-input 50-call attention
cycle by only 38.26%, below the unchanged 50% operator gate. Component diagnosis
found a bit-equal Torch merge faster than the manual Triton implementation.
C23 V2 passed 44 native tests, three executed four-rank suites, exact real-input
merge replay and the unchanged operator gate: 3477.473 to 1166.387 ms per cycle,
66.46% reduction, finite outputs and maximum relative L2 0.00201662 < 0.005.
This excludes FFN, changing-input quality, full-model timing and HTTP.
[Full 5s-00 evidence](c23-5s-00-execution-proof.json) records completed 50 steps,
134 input checks, expected cache/FFN/DLO counters and cleanup. Diagnostic HTTP
was 199.065 s; 39 frozen quality checks produced eight failures in visual/audio
similarity, reference/audio adherence, audio level and envelope. The fixed
profile is rejected; no 15 s or clean timing extension follows.
[Retirement proof](c23-retired-proof.json) records idle devices, free ports,
unchanged tested source, runtime v17 and frozen validators at 15:48:59 +08.

All 24 direction families are charged. The original 32 h / 128 logical-device-
hours and 2026-11-03 01:19 +08 deadline remain unchanged. All four final tracks
remain open; heldout requests remain sealed and no public publication occurred.
