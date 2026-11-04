# Lily assertion-backed cases

| Case | Route | Assertions |
| --- | --- | --- |
| integration/benchmark-cache-and-native-evidence | integration | 4 |
| integration/strict-config-request-and-state | integration | 4 |
| root/strict-offline-request | lily | 3 |
| sub-skills/model-runtime/checkpoint-shape-and-sequence-budget | model-runtime | 7 |
| sub-skills/model-runtime/same-bits-wrong-layout | model-runtime | 7 |
| sub-skills/qualification/audit-saved-production-record | qualification | 6 |
| sub-skills/qualification/benchmark-version-and-metric-boundaries | qualification | 6 |
| sub-skills/qualification/cpu-reference-is-not-gpu-proof | qualification | 6 |
| sub-skills/serving-cache/same-key-not-a-token-prefix | serving-cache | 7 |
| sub-skills/serving-cache/unsupported-stream-tools-and-last-role | serving-cache | 7 |

10 cases with 57 assertions. Every focused route has two difficult synthetic cases and source-native anchors; qualification also has a checkpoint/control case. Two integrated source-backed scenarios cross exact configuration/request/state and benchmark/native-evidence boundaries. No assertion is an executed Rust/GPU/model result.
