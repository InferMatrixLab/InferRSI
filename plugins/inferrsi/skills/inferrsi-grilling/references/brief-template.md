# Confirmed task brief

Use the applicable fields to summarize the decisions in the conversation.
Keep prior answers and evidence links; mark missing facts as unknown. This is a
human-readable handoff to existing task/protocol inputs, not a new runtime schema.

- **Requested deliverable:**
- **Target:** repository, framework, baseline, model/revision, hardware and runtime
  facts, with sources where inspected.
- **Workload and measurement scope:** representative inputs, load and metric.
- **Objective and tradeoffs:** priority, service constraints and acceptance gates;
  identify supplied gates and any calibration needed to derive missing ones.
- **Quality contract:** oracle/checks, precision, acceptable output changes and
  current validation gaps.
- **Permitted changes and preferences:** editable areas, deployment/dependency
  limits, upstream and maintenance requirements.
- **User-reported experience:** prior attempts, observed conditions, evidence and
  retry conditions; separate unsupported explanations from observations.
- **Hypotheses and unknowns:** what needs measurement or verification.
- **Resources and stopping:** devices, time/cost, stop conditions and final retest
  allowance.
- **Proposed next step:** bounded diagnostic/calibration or experiment, its inputs
  and required checks.
- **Delegated decisions:** choices the user delegated and the choices made.

Ask the user to confirm this brief or identify corrections. Retain the confirmed
scope for the current task; carry it into the original InferRSI workflow.
