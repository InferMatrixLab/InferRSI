# Trusted benign probe succeeds with explicit loader policy

Refs [Issue #67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**INCONCLUSIVE for generated-code execution, task quality and E2E.**

CPU2006 completed0:0 in68seconds on4CPUs/zeroGPUs and released its allocation.
The separately versioned scanner uses a cleared subprocess environment with the
registered base lib directory. The sandbox deliberately sets its matching
relocated readonly directory after clearenv. This policy was independently
reviewed; CPU2005 did not establish that Python imports require that setting.
Missing dependencies, unexpected external paths and now nonzero ldd returns
remain fatal. The original frozen bundle, trusted probe and installed packages
were reused without changing their bytes.

The actual trusted probe exits0 without timeout or stderr. All12 checks pass:
new namespaces, absent host paths, readonly runtime/root, blocked network with
only loopback, no-new-privileges, zero effective capabilities, namespace UID,
cleared synthetic inherited variable, relocated Python, single-CPU affinity and
the specified per-process rlimits. EvalPlus0.1.0.dev1, NumPy2.5.4 and psutil7.2.2
import successfully; the small trusted NumPy sum returns5.

Before/after rootfs JSON is byte-identical:25,241 entries with a recomputed
readonly-bind-set digest. All43 tracked EvalPlus Python files match the pinned
source. The97-distribution package audits are identical; all12 postflight checks
succeed, including old/new freezes, script/binary identities and source checks.
The full inventories and private mount locators stay in controlled storage,
bound by the report's hashes. Public probe output and executed source bytes are
retained. These observations cover this trusted probe and its tested invariants;
they do not certify every dependency, adversarial cleanup, aggregate resource
enforcement, answer secrecy or arbitrary generated-code containment.

The five local mocked loader controls were independently rerun before execution.
Their initial fixture failed because a local temporary lexical path was not
resolved; that source is retained. Correcting the fixture to use resolved roots
matches the existing inventory entry point, without a runtime change for that
fixture failure.

No full evaluator, benchmark data, generated model code or model ran. No measured
E2E effect. Next separately bind the synthetic evaluator trial to this completed
reference and its loader policy; the older conditional launcher is not activated
by this result. Readiness remains2388/7200GPUseconds with initial147separate.

KnowledgeStore candidate `case.qwen38-eval-sandbox-preparation-cand` revision `sha256:095a2b664b624afb2f613cb7ec19b124d1b3668546e61d5abdb81ef7d53cdeea`; readback verified.
