# Failure and recovery

| Observable symptom | Likely boundary | Next action |
| --- | --- | --- |
| No module named torch or local torch shadows installation | Interpreter or current directory mismatch | Run the root inspector outside the checkout; select the intended interpreter; inspect distribution metadata before reinstalling. |
| DLL load failed / undefined symbol | Torch/extension/compiler or runtime ABI mismatch | Compare wheel tags, build git version and extension build; rebuild only the affected extension against the selected torch. |
| nvcc not found / no kernel image | Missing source toolkit or unsupported architecture binary | Distinguish runtime use from extension compilation; install/select compatible toolkit or rebuild for actual architecture; preserve backend block meanwhile. |
| CMake ignores an environment knob | Removed setup.py control or not forwarded | Use the pinned pyproject and forwarding rules; set a supported cmake.define option explicitly, never guess obsolete flags. |
| Build killed or host unresponsive | Parallel C++/CUDA compile exceeds RAM/disk | Lower MAX_JOBS, inspect resource demand and resume a scoped build; do not delete an unrelated environment or entire workspace. |

Use [workflows](workflows.md) for inputs, expected outputs and checks. Record the actual error and environment; these hypotheses are not diagnosed root causes until the discriminating check supports them. Missing required device/runtime checks remain BLOCKED_REQUIRED_BACKEND.
