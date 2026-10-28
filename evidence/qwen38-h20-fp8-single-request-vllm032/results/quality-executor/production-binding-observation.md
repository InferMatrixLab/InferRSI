# Production quality binding and runtime inventory

Issue67 harness-only preparation. The delegated adapter now accepts the original
32/164 cohorts and authenticates actual quality-v5 export, dataset, protocol,
qualification and stable result bytes. It preserves official EvalPlus defaults,
source data, answers, tolerances and per-case timing. A pending record is never
scoreable; successful terminal/scheduler and twelve postflight checks are
required before metadata-only sealing. No all-canonical-pass gate was added.

The parent independently reviewed the14-source manifest
5911860f01e7bc6bc54d6f2da582ac4cba4e9d59b691613c8cdc33d176039bb6
and reran17pureCPUcontrols, including the unchanged v5 scorer consumer. Three
isolation/supervision helpers and the v5 provenance reader are byte-identical
to earlier reviewed snapshots. Source preparation style failures were retained.

CPU2137 failed1:0/1s,4CPU/0GPU before inventory: the new metadata-only wrapper
assigned TASK_ROOT without exporting it. The Python inventory therefore raised
KeyError. Original source/output retained. Wrapper v2 adds export, with no change
to the production adapter, dependencies or resource policy.

CPU2138 completed0:0/45s,4CPU/0GPU. Runtime inventory has25253entries and digest
sha256:b0ec2f42b1e415e04dbe89c1d2aae50b2a33cefaf5e8e75a41f7280bd81c34a2.
All25241non-executor entries exactly match the actual2024runtime inventory.
Only12declared executor files form the new source identity. Resource/evaluator
policy differs from the full164pilot only in scope/qualification metadata.

A qualification/protocol proposal is being reviewed using the actual2014 bounds,
2018 official external-export,2024 full164 capacity and2117 failure-classification
evidence plus this source/consumer review. No new production entry or model code
has executed yet, and the proposal is not activated. Original2024 FAILED and its
seven official HumanEval32 assertions remain preserved. This record does not
claim new runtime execution, model quality, performance parity or campaign PASS.
