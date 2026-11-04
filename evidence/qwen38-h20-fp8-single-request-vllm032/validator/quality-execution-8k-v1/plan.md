# Frozen quality execution protocol

Issue67 owner-approved quality policy remains unchanged: thinking disabled,
greedy, natural EOS, at most2048output tokens. GSM8K1319, HumanEval+164 and
subject-stratified MMLU1000; fixed iteration subsets100/32/100 are disclosed
within those final sets. Each final candidate score must be at least its matched
baseline minus0.01absolute; exact counts, no cross-task averaging or rounding.

Reuse the original prepared-v2 inputs and tokens. The original and v5 prepare.py
are byte-identical. Their protocol.py differs only by listing the added
sandbox_provenance.py in validator_identity; all prompt/cohort/token construction
is unchanged. The new source-manifest.json binds the exact v5 tools, original
prepared/cohort/tokenized manifests and authenticated generation config. No
dataset download, re-sampling, prompt change or answer inspection for tuning.

Baseline generation command: one H20,8CPU,96GiB request, at most9000GPU-seconds
from the already approved baseline phase. Submit only if the prior baseline
performance job is terminal and measured phase consumption plus9000≤14400.
Collector deadline7800s+60s cleanup; pre/post identity checks400s+5s each;
Slurm02:30:00 is the total cap. Server startup≤1200s and each sequential HTTP
request≤1800s, all within the collector limit. No retries or post-result sample
exclusions; timeout/missing output is INCONCLUSIVE. No performance timing claim
from these quality requests.

Same installed vLLM0.32.0, authenticated official FP8 model/tokenizer and runtime
as the formal baseline. Same default server optimizations with max length10240,
prefix caching disabled and text-only execution. All retained quality inputs fit
this context including the maximum requested output. Full byte/source guards,
exact SSE accounting, natural EOS identity, owned cleanup, postflight and
terminal scheduler receipts are required. Raw model outputs stay private.

The unchanged v5 scorer first scores GSM8K/MMLU and exports HumanEval code without
executing it. Only the separately frozen production adapter runs that export,
on CPU under the existing readonly isolated runtime. It supports both original
32/164 cohorts, official EvalPlus defaults and 3300s whole-batch wall limit. The
final record is sealed only after successful scheduler/terminal/postflight and
complete stable results. Official task fail/timeout stays a model score;
infrastructure failure, missing results or changed identities stays INCONCLUSIVE.

qualification.proposed.json is a review proposal for this exact executor
identity, using unchanged runtime/supervision plus actual2014/2018/2024/2117
evidence and independent production-adapter source/consumer review. It records
that the new production entry has not yet executed, and preserves2024's original
failed canonical-all-pass assumption. No new canonical100% gate or tolerance
change. Independent review is complete; this final content lock activates the bounded execution protocol when its digest is recorded in Issue67 before submission.

Search may begin only after this complete scorer/executor/data/command binding,
approved statistics and retrieval/performance protocols are frozen. A baseline
performance batch or a source-only draft is insufficient to award campaign PASS.

The same owned baseline service then serves the original ten 8192-token retrieval
inputs (selected unchanged from the original thirty-input fixture). The original
four-position JSON scorer is copied byte-for-byte as an AST source segment from
retrieval_baseline_v3.py. Full raw SSE, input and generated token identities,
usage and natural-EOS accounting are retained. Baseline needs at least9/10complete
hits; candidate complete and all four position counts must not regress. No new
inputs or scorer adjustment. The ten requests share the same9000second allocation
cap and7800second collector deadline; no extra budget. The earlier8K10/10observation
remains historical evidence, while this run will supply the matched baseline.

Review completed before execution; this protocol fixes original8K retrieval, task datasets, evaluator, natural-EOS generation and resource bounds. Formal performance uses the separately approved TTFT/TPOT paired statistics. Model quality and full campaign remain INCONCLUSIVE until actual complete evidence.
