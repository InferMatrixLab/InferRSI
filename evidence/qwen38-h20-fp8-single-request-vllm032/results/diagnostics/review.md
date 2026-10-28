# Independent review of bounded repairs

Reviewer: Codex reviewer subagent `review_fp8_graph` (read-only; no edits or GPU work).
Base: `eb56fbb05ef7d56756d98b8bac546e8d0264b2cf`.
Configured-backend commit: `4cdfd11f3f1602c27c94c2a7f7e13a5ba7a9d2c8`.
Reviewed head: `0f8ab73a3cc0d3f21099bc37f5a800e0633f7c32`.

The reviewer inspected both commits and consumers, plus the diagnostic observer
and job 1935 raw artifact/hash. No introduced blocking correctness defects were
found. The reviewer independently verified matching teacher-token sequences
between jobs 1925 and 1935, initial prefill equality in all three cases,
fixed-capacity eager/replay equality in 48/48 steps, compact/buffered equality
in 35/48 steps, and all-arm greedy equality in 48/48 steps.

Recommendation: accept the bounded repairs after the pending CPU suite passes,
while retaining campaign INCONCLUSIVE. The observer uses hooks, all three
prompts use bucket1024, and it bypasses HTTP and RequestRunner prewarm/reuse.
Production lifecycle, capacity transition and remaining decode differences
must be assessed before broader Graph qualification. No performance or service
acceptance claim is supported.

Post-review evidence: CPU job 1937 completed with 156 passed / 1 skipped;
the skipped test requires the separately gated GPU contract environment. No
source changes were made after review. This closes the review's CPU-suite
condition, not the remaining service/quality gaps or campaign acceptance.
