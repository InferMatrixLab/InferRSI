---
name: profiling-and-debugging
description: "Profile PyTorch operators and memory, benchmark controlled workloads, diagnose compiler stalls, nonfinite results and asynchronous device failures."
metadata:
  inferrsi: |
    {
      "profile": "local-skill-v1",
      "schema_version": 1,
      "kind": "skill",
      "origin": [
        "external"
      ],
      "status": "candidate",
      "empirical_validation": "not_run",
      "license": "NOASSERTION",
      "disable-model-invocation": true,
      "metadata": {
        "disco-role": "operating"
      },
      "tags": [
        "pytorch",
        "profiling-and-debugging"
      ],
      "sources": [
        {
          "type": "git",
          "url": "https://github.com/pytorch/pytorch",
          "commit": "9a90a4fefcaafa63ac984621963a6fcc66aee68c",
          "paths": [
            "torch/profiler/profiler.py",
            "torch/utils/benchmark/utils/timer.py",
            "torch/utils/collect_env.py",
            "docs/source/notes/numerical_accuracy.md",
            "docs/source/notes/randomness.md"
          ],
          "readset": "../../references/source-readset.json"
        }
      ],
      "applicability": {
        "scope": "Profile PyTorch operators and memory, benchmark controlled workloads, diagnose compiler stalls, nonfinite results and asynchronous device failures.",
        "prerequisites": [
          "An explicitly selected installed torch environment; actual devices for backend-specific checks."
        ],
        "input_contract": "A bounded model, tensor, data or environment reproduction and expected behavior.",
        "produced_artifact": "Produce a reproducible trace or timing design and a claim bounded by the measured workload.",
        "failure_modes": [
          "Transferring source facts to another wheel or backend without checking drift."
        ],
        "refusal_point": "Withhold backend success when the required device check cannot execute."
      },
      "limitations": [
        "Source-supported procedures are not full-repository execution coverage.",
        "Required unavailable backends retain BLOCKED_REQUIRED_BACKEND; no measured efficacy claim."
      ],
      "consumption_mode": "packaged"
    }
---

# Profiling and debugging

Use this route for the task named in the description. Produce a reproducible trace or timing design and a claim bounded by the measured workload.
This is a source-derived **candidate**, with native backend checks separate from
source support. Read the root [provenance](../../references/repo-provenance.md)
when package, API or platform identity differs.

## Operating sequence

1. Record the concrete input contract, current behavior, desired result, package
   version and backend. Preserve a tiny eager or single-process control.
2. Read [workflows and mechanisms](references/workflows.md) and choose its
   matching branch. Check prerequisites before launching a build or device job.
3. Apply the smallest change at the first disagreeing boundary; preserve tensor
   shape, dtype, layout, device, mutation and gradient assumptions.
4. Check the predicted output and failure recovery using the linked helper or
   recipe. A software check cannot establish an unavailable device capability.
5. Return the artifact named above, checks actually run, unresolved conditions
   and the next discriminating check. Missing required backend execution stays
   **BLOCKED_REQUIRED_BACKEND**; efficacy stays **not_run** without measurements.

Read [troubleshooting](references/troubleshooting.md) when a prerequisite or
check fails. The references contain complete procedures and exact source
permalinks; the original source checkout is not a runtime prerequisite.
