# Frozen historical task and grader

`task/` and `runner/grade.py` preserve the original bytes used by the experiment.
Their hashes are checked against `../plan/publication.json` and the public bundle
integrity map. Source revision and omitted source identities are also retained.
These files explain and permit review of the mathematical, input and timing
protocol; they are not a portable launch command or a test of the PR's new
TaskPackage. Host-specific launch configuration is deliberately not published.

`../verify.py` is a separate, CPU-only publication checker. It recomputes all
case medians, speedups, best-so-far states and token sums; verifies source and
bundle bytes; and checks counts/selection against the public audit extracts.
It never imports candidates, runs the frozen grader, starts a device job, or
changes a historical verdict. Full raw rank calls, original condition audits
and session logs remain external and are explicitly unavailable in this checkout.
