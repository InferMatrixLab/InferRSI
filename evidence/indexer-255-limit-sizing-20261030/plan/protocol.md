# Issue #255: defer serialization of already-limit-omitted views (proposal)

Status: prospectively accepted by coordinator before candidate/measurements, with independent reviewer conservative subclass guard. Baseline f93df0548a26714f6514337a8525c7c14108acad. Plane: harness. Historical cache v1 FAIL and confirmation uncertainty remain unchanged; this is a distinct, smaller optimization, not another attempt on that cache.

## Hypothesis and scope

`KnowledgeReader.collect.select` calls `len(_json(view))` before checking `len(selected) >= limit`. Once the item count is full, that byte size cannot alter the `output_limit` omission. Move only the full-count check before serialization for exact type(bundle) is Bundle; subclasses retain the original serialization/error path. Leave byte-budget checks after serialization. Do not skip `_read`, `Bundle.view`, identity/revision/resource validation, filters, ranking, query processing, omitted-item ordering, or context selection. No memo/cache, source/corpus edits or ranking changes.

For N calls to select and no max_bytes, view-size JSON serialization reduces from N to min(N,limit). With max_bytes, only calls after count saturation are removed; byte-budget-excluded candidates before saturation still undergo exact size calculation. Manifest and complete-resource hashing remain O(N*resource_bytes); no claim of removing that dominant work.

## Before performance execution

Independent source/protocol review; synthetic call-count and full JSON parity tests, including default, relevance, explicit order, aliases/revisions, material, context, exact/undersized byte budgets, invalid resources after count saturation, mutable inputs, filters and no match. Invalid limit values (0, None, negative, bool) retain their existing rejection. Supported normal Bundle outputs already serialize their metadata/resources/dependencies into the revision before select; custom overridden view behavior must be considered explicitly rather than hidden.

Freeze candidate commit, runner hash, exact cases and installed/import-path proof before timing. Run existing relevant software tests. No semantic heldout evaluation or new labels. Any correctness discrepancy stops before performance. Independent resource/output audit uses saved captures only.

## Fixed workload

All arms use same Python, source imports pinned to each worktree, identical packaged corpus, no filters unless stated, limit=5, max_bytes=None, material=False.

1. Primary: reused-reader default Collect(query=''); one warmup then one call per sample. This broad, bounded enumeration is the direct targeted operation, not a claim about every query.
2. Secondary: reused-reader Collect(query='', relevance='memory', context_bytes=262144); one warmup then one call.
3. Secondary: fresh-process CLI default Collect(query='', limit=5), full parent-observed startup/stdout capture.
4. Untouched guard: fresh-process CLI catalog search(query='cgroupv2', limit=5), same exact command/API mapping as old study.

Exact CLI argv: [PYTHON, '-m', 'inferrsi', 'collect', '', '--limit', '5', '--json'] and [PYTHON, '-m', 'inferrsi', 'knowledge', 'search', 'cgroupv2', '--limit', '5', '--json']. Each child gets only PATH=os.defpath, PYTHONPATH=<arm>/src, PYTHONDONTWRITEBYTECODE=1; cwd is its matching arm root. Freeze runner manifest before candidate measurements. Both arms serialize identical results; retain complete correctness output once per path plus every timing sample digest/bytes.

## One study only

120 paired groups, balanced AB/BA shuffled with random.Random(25530), path order fixed 1→4. Sequential isolated arm subprocesses, no concurrent heavy work. Capture wall nanoseconds and process CPU nanoseconds for API; child CPU user/system from os.wait4/rusage-compatible subprocess accounting for CLI plus wall time. Record monotonic chronology, arm order, source/corpus hashes before/after, load averages as contextual metadata. CPU and load evidence can narrow attribution but cannot waive a wall-time failure. Fresh process is not cold filesystem cache.

No trimming, pooling with old studies, retries to obtain PASS or tuning after outcomes. Exactly one execution after freeze. Missing/changed-source samples → INCONCLUSIVE; preserve partial data, no replacement.

## Prospective gates (proposal requiring coordinator acceptance)

- All output/resource/contract parity gates must pass.
- Primary median within-pair latency reduction >=5%, bootstrap95% lower bound >0. This practical threshold is specific to this smaller eliminated-serialization hypothesis, not relaxation of historical cache gates.
- Secondary each p50 regression <=10%, p95 regression <=20%; nearest-rank p95. Additionally upper95% bootstrap bound on each secondary p50 regression <=10% to exclude the median uncertainty that prevented previous acceptance. Point-limit failure → FAIL; point gates pass but confidence bound exceeds limit → INCONCLUSIVE (not PASS).
- 10,000 paired-group bootstrap resamples, seed25531, percentile2.5/97.5; no arm-independent resampling. Ratios of resampled medians for secondary p50. p95 confidence intervals descriptive, never SLO claim.
- Any source/corpus/parity/correctness failure blocks promotion regardless of speed. No ranking accuracy gain inferred; #255 accuracy remains independently open.

## Deliverable / stopping condition

One table with primary/secondary wall and CPU metrics, exact counts, bootstrap uncertainty, output parity and deterministic serialization counts. If practical gain is absent or any gate fails/inconclusive, retain evidence and stop this candidate without another confirmation. If all pass, seek current-head independent review and publication approval; no automatic tracker closure. No model/service/hardware calls or remote writes in this preparation.
