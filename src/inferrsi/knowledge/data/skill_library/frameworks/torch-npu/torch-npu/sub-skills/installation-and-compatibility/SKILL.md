---
name: installation-and-compatibility
description: "Select a compatible TorchNPU, PyTorch, Python, CANN and driver stack; distinguish released wheels from source builds and diagnose import failures."
---

# Install and qualify TorchNPU

Use for a new Ascend environment, version mismatch, wheel/source build decision,
or missing CANN library. Start with [the stack procedure](references/stack.md).
Use [failure recovery](references/troubleshooting.md) before changing packages.

Inputs: hardware family, Linux architecture, driver/firmware/CANN versions,
Python ABI, exact torch/torch-npu builds, binary versus source intent, and access
to the device. Output: one explicit compatible stack proposal, installation
commands and separate import/device observations.

1. Separate the released package matrix from the source branch's build lines.
2. Establish driver, CANN and environment setup before package import.
3. Install matching PyTorch and TorchNPU package lines in a private environment.
4. Run [the bundled probe](../../scripts/inspect_environment.py) without device
   execution, then use `--device` only on an authorized NPU host.
5. Record actual versions and all blocked checks; route missing backend
   registration to [dispatch](../privateuse1-and-dispatch/SKILL.md).

Source-derived candidate: no wheel install, source build or NPU operation was
validated by this contribution. A clean pip dependency report is insufficient
to qualify the CANN/driver/device combination. Preserve `BLOCKED_REQUIRED_BACKEND`
when the actual Ascend environment is absent.
