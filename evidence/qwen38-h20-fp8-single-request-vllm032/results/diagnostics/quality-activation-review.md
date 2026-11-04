# Quality preparation activation review

Refs [Issue67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**INCONCLUSIVE. No model quality score or generated-code execution.**

Independent read-only audit verified all eight archived v2 helper hashes against
the preparation manifest. Dataset/cohort preparation counts are1319 GSM8K,
164 HumanEval+ and1000 MMLU; CPU preparation remains distinct from evaluation.
No final-set contents or outputs were inspected during this review.

Three blockers remain before activation:

1. The archived SSE parser treats `prompt_token_ids:null` on later choices as a
   repeated echo. Replay of both ordinary and coalesced raw readiness streams
   fails. Removing only these null optional fields in an in-memory diagnosis
   lets the128K8-token/7-choice example parse. Preserve archived v2; fix a new
   version that requires exactly one non-null first-choice echo. Coalescing
   itself is already supported by this quality parser.
2. Arbitrary non-EOS output IDs with finish_reason=stop pass the current parser.
   Bind effective EOS/stop configuration and independently authenticate natural
   EOS versus capped termination before claiming workload integrity.
3. HumanEval+ still has no qualified generated-code executor. Namespace
   availability and a proposed benign probe are insufficient. The scorer's
   image_digest declaration cannot stand in for the proposed bubblewrap
   readonly-bind rootfs_digest. Qualify actual containment, resource/descendant
   cleanup and exact full base+Plus invocation, then use a truthful versioned
   provenance contract and bind samples, dataset and results.

Missing/duplicate responses, raw/summary mismatch, invalid counts and missing or
repeated DONE fail closed in the inspected helpers. Exact per-task comparison
implements one percentage point as at most13/1/10 lost correct items for these
three final denominators. No bar is changed by identifying these gaps.

The original source archive and manifest are retained privately. Archive SHA256:
9c9cddd3242c00b6c39e4a6342a4ab7d17ab3e74f07bbd7c628c6952f4517099;
manifest SHA256:4ac94ae332467ab7d3221906c571ada1836ec45382159d8677cf9f30e36c8c9f.
This is failed compatibility/unfinished qualification evidence, to be followed
by prospective repairs; no old artifact is rewritten or reclassified as PASS.

KnowledgeStore candidate `case.qwen38-quality-activation-gaps-cand` revision
`sha256:eaf0aee4c2a45c339daf99c70ef9a92c24dfc1118963ed67fd30f623eeeabcd3` was written and read back exactly; no library promotion.
