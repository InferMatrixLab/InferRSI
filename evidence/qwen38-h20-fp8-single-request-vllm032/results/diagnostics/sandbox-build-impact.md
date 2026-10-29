# Reviewed dependency wheels: bounded CPU build completed

Refs [Issue67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**INCONCLUSIVE — dependency preparation only, no sandbox or quality acceptance.**

The rejected initial resolve draft and CPU1985 no-wheel failure remain recorded.
The repair separates source building from dependency resolution. Independent
review authenticated the wget3.2 and tempdir0.7.1 archives against PyPI, verified all extracted file bytes, reviewed both setup
scripts, and verified the five-tool lock.
Neither source declares install/setup dependencies or custom build commands.

CPU1986 completed0:0 in89 allocated seconds,4CPUs/zeroGPUs, and the allocation
was released. A new dedicated Python3.12.13 build environment installed exactly
the five hash-locked tools from PyPI using wheels only. The two explicit source
builds then ran with uv0.11.13 offline and build isolation disabled. Offline
describes those build commands, not the preceding tool installation. Both wheels
were created without changing the input archives or the baseline/native runtime.

Parent and independent review authenticated the complete output manifest and
wheel contents. Each wheel contains only the original module and four metadata
files; module bytes equal the reviewed source archives. Names, versions, pure
Python tags, absent runtime dependencies, and every RECORD hash/size match.
No duplicate, escaping or symlink entry exists. Exact output and tool identities
are retained in sandbox-build-1986.json; the reviewed script and build-tool lock
are retained under patch/diagnostics/ and plan/.

This supports using these exact wheels in a future no-build dependency resolution.
It does not establish a complete runtime lock, installed EvalPlus, working sandbox
or full HumanEval+ evaluation. No model, task dataset, generated solution or full
evaluator ran. Outputs still need binding into the next reviewed resolver plan;
no gate or performance-search activation follows from this preparation.

There is no measured E2E performance effect and no GPU budget change: readiness
remains2388/7200GPU-seconds, with the earlier147seconds separate. The knowledge
record retains the initial design rejection,1985 failure and1986 build completion.

Sources: [wget3.2](https://pypi.org/project/wget/3.2/#files),
[tempdir0.7.1](https://pypi.org/project/tempdir/0.7.1/#files), and
[uv0.11.13 CLI source](https://github.com/astral-sh/uv/blob/0.11.13/crates/uv-cli/src/lib.rs).

KnowledgeStore candidate `case.qwen38-eval-sandbox-preparation-cand`: `sha256:358d2d803c0a12e9bec479ed60ce59cf3aa897e912dea4f52c38bedced084abb`; readback verified.
