## Select supporting skills from observed evidence

Load the skill whose trigger is observed. Check its revision, prerequisites and
scope before using its output. If none fits, search the observed component and
symptom, then verify any result against the actual model, engine, OS and device.

| Observation in this run | Load skill ID | Returned evidence and next decision |
| --- | --- | --- |
| The failure resembles a prior trial or appears only with a particular optimization. | `inference-optimization-casebook` | Get the prior failure conditions and retry rule. Test whether the same switch reproduces the signature on this target. |
| Ascend timing or device behavior changed after a killed job or card-group change. | `ascend-device-health` | Collect device health, occupancy and timing checks. Establish a clean matched control before blaming the engine. |
| A vLLM V1 request stalls during asynchronous KV transfer, preemption or block reuse. | `audit-vllm-kv-lifetimes` | Build the scheduler/connector ownership trace. Probe the earliest missing completion or block-release edge. |
| A CUDA AFD dense FFN P2P exchange hangs or returns the wrong slice. | `audit-afd-p2p-exchanges` | Build the rank and per-peer payload ledger. Check the first mismatched assignment against caller traces before testing transport. |

