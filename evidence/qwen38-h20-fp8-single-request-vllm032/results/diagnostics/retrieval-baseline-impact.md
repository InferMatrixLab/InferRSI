# Baseline retrieval qualification outcome

Refs [Issue67](https://github.com/InferMatrixLab/InferRSI/issues/67#issuecomment-6347838911).
**INCONCLUSIVE — baseline qualification only, no candidate or activated gates.**

| Input tokens | Complete cases | Exact matches at each of four positions | Generated tokens |
| ---: | ---: | --- | ---: |
| 8192 | 10/10 | 10/10, 10/10, 10/10, 10/10 | 1289 |
| 65536 | 10/10 | 10/10, 10/10, 10/10, 10/10 | 1236 |
| 131072 | 10/10 | 10/10, 10/10, 10/10, 10/10 | 1241 |

Job1968 completed0:0 in879 allocated GPU-seconds, one GPU, allocation released.
The v2 homogeneous/nonrepeating inputs and v3 observer were bound prospectively.
The run used unchanged vLLM0.32.0 default optimization choices, no OMP override,
greedy natural EOS with maximum2048, and the authenticated official client.
All30 raw streams were independently re-read locally: exact prompt echoes,
output IDs/usage, unique final DONE, final stop, official-client text/timing and
fixed scoring agree. Nine128K requests coalesced multiple tokens into one choice;
no requests were dropped, retried or regenerated. Full raw SSE/client/server
records remain in controlled storage; their identities are in the summary.
The shared observation JSONL is byte-identical to the original and contains no
private operational paths or device identities.

All30 final IDs are248046; authenticated generation_config declares EOS248046
and248044, and every final choice has stop_reason:null. This post-run audit
supports observed EOS termination; a prospective full termination validator
is still required before acceptance. No historical validator or score changed.

Startup was119.138485 seconds. Descriptive median TTFT/whole latency were
1.678214/3.028684 seconds at8K,18.607111/20.278450 at64K and49.168697/51.341158
at128K. Natural-EOS outputs totaled3766 tokens. These are retrieval costs,
not the required2048-token performance matrix, a paired speedup or parity claim.
No production engine patch was made by this attempt.

Observer cleanup reports server0, forced=false and no owned group remaining.
Server logs show30-second drain and manager shutdown, without observed kill
escalation, but one multiprocessing semaphore cleanup warning remains. Preserve
that limitation; do not label teardown entirely warning-free.

Readiness total is2388/7200 GPU-seconds (0.663333/2GPU-hours), with4812 seconds
remaining. The separate initial147-second authorization is unchanged. Baseline4,
search8 and finalization30GPU-hour stages remain unused and reserved.

During independent local audit, an initial check incorrectly equated the
observer's default-spaced JSON prompt digest with the fixture's compact JSON
digest. Exact echoed IDs were already equal. The corrected audit verifies both
serialization-specific digests separately and compares actual ID arrays; no
source inputs, responses, raw hashes, valid flags or scoring were rewritten.

The proposed owner policy remains baseline>=9/10 complete per length and
candidate no regression against matched baseline complete/per-position counts.
This observed baseline is10/10, so that policy would require candidate10/10 at
each length. Owner confirmation and complete validator freeze remain pending.

KnowledgeStore candidate `case.qwen38-retrieval-construction-cand` revision
`sha256:3e1c05db461c9002bdf1af8065adc39b6eb30a662ace24d44ea81735be89f62d` was written and read back exactly; no library promotion.
