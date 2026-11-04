# First measured native E2E effect

Governing Issue67; single fixed input diagnostic; **INCONCLUSIVE** for formal service acceptance, task quality and vLLM parity.

Engine runtime8859ef319486eb5ed4a444fc66c1018cbebbab33 was tested on the same physical H20 using the same installedruntime, pinnedofficialHTTPclient and n8192-s0 input. Bothnativearms completed8192input/2048output,ignoreEOS,concurrency1,after8192/16warmup. The complete2048outputtoken sequences match for this synthetic input. Counts/prompt echoes/terminal/usage/client timings and rawSSE hashes were rechecked. This is not general task-quality evidence.

| Arm | TTFTseconds | TPOTmilliseconds | Requestseconds |
| --- | ---: | ---: | ---: |
| OriginalTriton |151.348310384|98.866396722|353.727824473|
| FlashInfer smallM |151.348666037|50.836547537|255.411078846|

Descriptivecandidate/controlratios:TTFT1.000002350,TPOT0.514194400,request0.722055380. Onecase/one repetition perarm; no variability or formal10case/3repeat inference. Nativepostflight active/state counts werezero and bothownedprocessgroups stoppedwithoutforce. Defaultbackend remains unchanged.

The fulljob FAILED124:0 after1320GPU-seconds: the outer1300-secondHTTPtimeout interrupted the vLLM arm during startup/Graphcapture. No vLLMrequest or explicitobservercleanuprecord was produced. Slurmreports the allocationreleased; do not claim gracefulbaselinecleanup or a completedparitycomparison. Keep this partialresult and timeout unchanged.

Sixoperatorcontrols hadfiniteoutput and exact changed-inputGraph/eager results. M32usedTriton; onlyM1/M31 qualify actualFlashInferdispatch in this run. Realprojectionmicrobench observations are not general modelquality evidence. Prefill remainedTriton and dominatesTTFT. Thegraphbucket ceiling also causesdemotion during2048-token output; this request measures that deliveredbehavior, not a fullGraphdecode claim.

Nano-vllmPR11 head a23bfc61f7c946879c8b64c67d5dade2e530ed5f differs from testedruntimeonlyin Markdownheading/whitespace. CPU 108 checks remain applicable. Independent review rehashed the raw archive and all 27 extracted files, matched tested runtime source, and verified all four SSE/client records and cleanup. PR11 merged at 7f5e64d52dc91a66b4a68aadb56641f543d063c8 after review; no repository Actions/status checks were configured for its head. Issue completion remains open.

Budget after2076:2388earlier+1800conservative2041reservation+11actual2074+1320actual2076=5519/7200readinessGPU-seconds. Initial147seconds remainseparate. The44GPU-hourtotal is unchanged.
