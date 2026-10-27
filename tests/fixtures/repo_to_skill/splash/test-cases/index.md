# Splash assertion-backed cases

| Case | Route | Assertions |
| --- | --- | --- |
| integration/memory-cache-concurrency-and-quality | integration | 4 |
| integration/prefix-safety-and-benchmark-attribution | integration | 4 |
| root/offline-request | splash | 3 |
| sub-skills/qualification/acceptance-is-not-net-speed | qualification | 6 |
| sub-skills/qualification/precision-and-ane-control | qualification | 6 |
| sub-skills/qualification/same-machine-round-plan | qualification | 6 |
| sub-skills/runtime-planning/gguf-format-and-draft-compatibility | runtime-planning | 7 |
| sub-skills/runtime-planning/memory-cap-is-not-only-weights | runtime-planning | 7 |
| sub-skills/serving-cache/persistent-cache-after-model-change | serving-cache | 7 |
| sub-skills/serving-cache/same-prefix-different-cache-salt | serving-cache | 7 |

10 cases; 57 assertions. Every focused route has two difficult synthetic cases, with source-native anchors; qualification also has a model-identity control case. Two integrated source-backed scenarios cross cache, memory and qualification; these test guidance, not actual native execution.
