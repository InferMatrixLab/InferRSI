## Select supporting skills from observed evidence

Load the skill whose trigger is observed. Check its revision, prerequisites and
scope before using its output. If none fits, search the observed component and
symptom, then verify any result against the actual model, engine, OS and device.

| Observation in this run | Load skill ID | Returned evidence and next decision |
| --- | --- | --- |
| The supplied benchmark lacks an agreed workload boundary or modality quality oracle. | `inference-benchmark-design` | Obtain a workload and parity protocol. Resolve the missing gate and measure the baseline before comparing candidates. |
| A slow stage is visible but its contribution to the requested metric is unclear. | `performance-ceiling-analysis` | Estimate stage share and achievable headroom. Profile the next limiting stage if even eliminating this one cannot meet the target. |
| Several legal changes could address the profiled limit. | `optimization-search-policy` | Obtain a ranked shortlist with mechanisms, expected signals and cost. Test one bounded candidate, then retain or revert it using the paired evidence. |
| A prior trial appears to match the bottleneck or an earlier candidate failed. | `inference-optimization-casebook` | Retrieve the prior workload, decision and retry condition. Reuse its hypothesis only after comparing target conditions and retest on this run. |

