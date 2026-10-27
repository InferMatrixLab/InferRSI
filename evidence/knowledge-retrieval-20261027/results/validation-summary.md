# Local software and package validation

These are software checks reported by the accountable orchestrator for the
fixed runtime candidate, separate from the frozen CPU retrieval experiment.
This summary deliberately excludes private local paths and raw command logs.

| Check | Actual result and qualification |
| --- | --- |
| Whole local pytest run | **10 failed, 1,340 passed, 6 skipped, 2 errors, 135 subtests passed**, 953.11 seconds. This is a failed whole-suite run, not a green suite. |
| Focused failure recheck | The same eleven selected failing/erroring test functions, including parameter variants, were rerun separately on baseline and candidate. Each reported **9 failed, 4 passed, 3 errors**. The CRLF case was then isolated from earlier fixture pollution: both sides reported **1 failed, 1 passed**, with `ValueError: Skill metadata must remain unchanged`. All initial **10 failures and 2 errors** were thereby reproduced on the baseline; neither run becomes a passing whole suite. |
| Manifest regressions | All 20 newly added manifest tests passed in the local suite. The runtime author separately reported **80 targeted tests passed**; a separate selected baseline run reported **104 passed**. These scopes are distinct from whole-suite status. |
| Wheel and sdist | Default isolated builds succeeded. An earlier `--no-isolation` attempt failed because setuptools was unavailable in that environment; later isolated build success supersedes that build attempt, not the failed pytest run. |
| Installed artifact contents | All **469 packaged data files** matched the source byte-for-byte, and packaged runtime source matched the evaluated source. Wheel SHA-256: `4da1447422e5690573028373bda9baf8ab54b177031d7ba3d17586cb0533822d`. |
| Evaluation validator | Normal and optimized-Python synthetic selfchecks passed. Explicit source-label checks rejected an absent support marker under `-O`. Exact measurement-set checks reject missing/duplicate rows and pairs. Original two-pair baseline-v-baseline mechanics data passed the revised structural/parity recheck; these remain dry-run evidence. |

The orchestrator classified the local failures by their observed boundaries:
oversized parametrized pytest names exceeding Windows' 32,767-character
environment-variable limit; GBK decoding; four cases needing unavailable Bash;
two Windows short/long temporary-path cases; one asset-manifest snapshot case;
and a process-control case using unavailable `os.getpgrp`. The CRLF delimiter
harness case failed in the initial whole run, but produced a fixture teardown
error in the focused reruns after earlier fixture pollution. Preserve that
status difference rather than treating the focused counts as an identical
repetition of the initial run. Its subsequent isolated two-case rerun restored
the original failing behavior on both revisions. Those isolated test durations
are software-test execution time and are excluded from retrieval performance.

The candidate and baseline focused rechecks establish reproducibility of those
initial failures in this local environment. They do not establish Linux CI,
all-platform portability or untested application behavior. A clean supported
Linux environment should rerun the full suite, especially the shell/process,
path and fixture-sensitive tests. CI status and revision-scoped independent
review must be reported separately when available.

After evidence integration, **23 inventory tests passed** in 1.10 seconds; the
read-only inventory checker reported **no errors, 9 bundles and 120 hashes**.
`ruff check src tests tools` passed. A wheel-only, site-disabled smoke read
108 records and reproduced all four `DefaultStager` output hashes from the
formal candidate result. Its first harness attempt failed an unresolved
temporary short-path import-origin check before retrieval. Resolving the
expected path allowed the smoke to pass; that retry established no package
defect. Remote CI is pending at PR creation.

The complete 24-case and 20-pair formal results are retained separately in
`quality.json` and `benchmark.json`; both frozen gates passed. Software-check
counts, package hashes and dry-run timings remain distinct from those results.
