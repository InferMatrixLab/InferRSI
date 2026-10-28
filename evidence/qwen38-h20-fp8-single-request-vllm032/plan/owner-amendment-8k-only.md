# Owner amendment: 8K-only performance and retrieval acceptance

Refs [Issue #67](https://github.com/InferMatrixLab/InferRSI/issues/67).
The owner explicitly confirmed that both retrieval and formal TTFT/TPOT
acceptance cover only 8192 input tokens. This
prospective scope change supersedes the earlier required 64K/128K lengths.
Historical artifacts, source identities, observations, failed attempts and
verdicts remain unchanged. No old result is relabeled by this amendment.

The two engines still use the same pinned official vLLM0.32.0 streaming HTTP
client, authenticated official FP8 model/tokenizer, physical H20, concurrency1,
10 fixed 8K inputs, 2048 actual output tokens ignoring EOS and three paired
alternating repetitions. Candidate/baseline TTFT and TPOT must each be <=1.03.
Metric aggregation and variability handling remain pending owner confirmation.
The prior three-length reducer cannot be treated as the new activated validator.
A versioned 8K-only reducer and complete freeze are still required before search.

Retrieval retains the existing ten 8K inputs, all four positions and scorer.
The matched baseline has10/10 complete matches and10/10 at every position.
Candidate complete and per-position counts must not regress, thus10/10 is
required at8K. No resampling, input mutation or post-result scorer change.
The prior64K/128K short-output vLLM retrieval requests succeeded. The native
attention path has a static long-context memory limitation; full2048-output
performance acceptance was not established. The new scope follows the owner's
explicit choice and does not assert that the prior baseline requests failed.

GSM8K1319/HumanEval+164/MMLU1000 quality scope, frozen screening subsets and each
per-dataset one-percentage-point gate remain unchanged. Full164 CPU reference
preparation remains applicable. The approved44GPUh phased cap2/4/8/30 remains an
upper limit; actual GPU usage is2388readiness seconds plus147separately approved
initial seconds. Formal baseline/search/finalization stages remain unused.

Under the pending six-restart AB/BA/AB proposal, one8K warmup plus ten timed
requests per restart would produce60timed+6warmup requests=135168 output tokens,
compared with405504 in the older three-length proposal. This is a workload count,
not a measured time estimate or a new budget authorization. Cost estimates will
be revised after matching bounded measurements. No additional GPU is used by
this scope-record update.

Campaign remains INCONCLUSIVE. Evaluator qualification, statistical decision,
final source/runtime/command/validator freeze and full acceptance remain pending.
No search, quality PASS or E2E gain is activated. Autonomous reviewed PR merge
is authorized; final campaign acceptance and Issue closure remain owner actions.

KnowledgeStore candidate revisions (readback verified; no protected promotion):

- `case.qwen38-statistics-proposal-cand`: `sha256:dff55bb95214f4192c1fd4f8544c57be838a50a3ede294814be92f1bc24feff1`
- `case.qwen38-retrieval-construction-cand`: `sha256:90cbe064f0885f4bd2089e0b0c66e7445c2ddc7380b4ffb46bbbc5ab470c7d1f`
