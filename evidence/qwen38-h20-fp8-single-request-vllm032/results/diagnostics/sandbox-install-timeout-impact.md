# Installation timeout and misleading exit marker

Refs [Issue67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**INCONCLUSIVE — failed readiness attempt; no campaign activation.**

CPU1992 reached its 30-minute limit. Slurm records TIMEOUT, TimeLimit, exit0:15
and1820 allocated seconds,4CPUs/zeroGPUs; allocation release was checked. The
EXIT trap nevertheless wrote0. That marker is not completion evidence and must
never override the scheduler state or missing expected artifacts.

The preserved partial environment contains Python3.12.13 and only five build
tools: packaging26.3, setuptools84.2.1, setuptools-scm10.3.4,
vcs-versioning2.6.0 and wheel0.48.0. The92-package runtime installation did not
finish; EvalPlus installation, dependency checks, runtime inventory and trusted
benign probe were not reached. No evaluator, generated solution, task data or
model was executed. The partial environment and download cache remain retained.

The log shows repeated download attempts and eventually two completed-download
messages. Two bounded samples of the owned installer process showed about15.7MB
of wchar progress over103.7seconds before the timeout; this is process write-call
accounting, not network throughput or physical disk bytes. Lack of completion was
not treated as proof of a hang. Transfer, unpacking and storage contributions
have not been isolated, so no root cause is claimed.

Post-terminal metadata and hash checks were lightweight login-node reads. One
source helper invocation incorrectly supplied the expired job ID to pass its
environment guard. Its returned success authenticates only the checked bytes;
it is not an in-allocation validation and the invocation must not be repeated.
The retained output authenticates15 freeze entries; source-helper return status
and invocation context are operator-reported because that output contains no
independent command/return-code receipt.
No compilation, installation, model or evaluator execution occurred in that check.

The next proposal must preserve these artifacts, use a fresh environment and
the same reviewed source/locks, handle TERM/INT/HUP explicitly, and require an
explicit completed marker plus actual Slurm completion and expected artifacts.
Clear inherited Python overrides and use explicit version checks instead of
optimization-sensitive asserts. Lower download concurrency and a longer network
timeout are prospective transport hypotheses, not measured improvements.

No measured E2E performance effect or GPU budget change: readiness remains
2388/7200GPU-seconds, with the earlier147seconds separate. Statistical/retrieval
policy confirmation and complete campaign freeze remain pending. Readiness
failure is retained without converting the campaign verdict to PASS or FAIL.

KnowledgeStore candidate `case.qwen38-eval-sandbox-preparation-cand`: `sha256:3602c4b412d8fd02d84f937dc9eb9956bb41f8e8ba4921452bcdee455bb37ebc`; readback verified; all earlier attempts retained.
