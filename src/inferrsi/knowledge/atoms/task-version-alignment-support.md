## Select supporting skills from observed evidence

Load the skill whose trigger is observed. Check its revision, prerequisites and
scope before using its output. If none fits, search the observed component and
symptom, then verify any result against the actual model, engine, OS and device.

| Observation in this run | Load skill ID | Returned evidence and next decision |
| --- | --- | --- |
| Several upstream revisions changed a boundary and the first incompatible change is unknown. | `repository-evolution-analysis` | Trace the history to a candidate transition. Run the same contract test immediately before and after it. |
| The changed component is vLLM-Ascend and its release, role or effective dispatch differs. | `vllm-ascend` | Get the version-specific dispatch and first failing boundary. Verify applicability against the installed stack before choosing a pin or adapter. |
| An AFD Plugin upgrade changes a CUDA P2P rank map or per-peer split. | `audit-afd-p2p-exchanges` | Compare the old and new payload ledgers. Test the first changed rank or slice with the same worker configuration. |
| A release claim spans combinations with missing hardware or parity evidence. | `claim-contract` | Map each tested combination to its gates. Publish the observed matrix and retain untested cells as unknown. |

