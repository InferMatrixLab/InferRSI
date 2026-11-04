# Native evidence boundaries

No native compilation, Swift API execution, MLX inference, cancellation or GPU
test result is established by this skill. The source package needs Swift tools
6.2 and an actually resolved MLX Swift dependency. Source instructions use an
Xcode macOS package-test route, not `swift test`. The selected original tests
and their build artifacts are unbundled; checkout-specific commands belong in
an external native-candidate plan after whole-graph integration and permission.

## Original test assertions worth preserving

[`CancellationTests`](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Tests/MLXLMTests/CancellationTests.swift)
constructs and evaluates a tiny quantized Llama without downloading weights.
Its cases cover early stream break plus producer join, immediate producer
cancellation plus drain/join, final `.cancelled` reason, and a 7-token limit
reporting `.length`/count 7. These execute the real MLX model/backend, not just a
host-record parser. The test name alone does not force Metal: actual device,
build and executed test counts must accompany evidence. Nonhang/join assertions
are not a recorded GPU dispatch/backgrounding trace.

[`GenerationExecutionTests`](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/Tests/MLXLMTests/GenerationExecutionTests.swift)
uses a custom iterator with explicit next/finalize hooks. Source assertions
cover independent per-generation progress, task-local context surviving the
executor hop, MainActor caller not running iteration on the main thread,
cooperative-worker availability, one cancellation not cancelling another,
consumer cancellation reaching blocked iteration, empty iteration still
finalizing and finalization before producer join.

The cancellation-during-next case blocks inside a step, cancels its task,
releases the step, then asserts one recorded token 42, `.cancelled`/count 1 and
finalization. It directly contradicts the assumption that cancellation must
retroactively suppress a step already entered. The device-override case
explicitly uses CPU and checks task context/control flow; that is not Metal
qualification. The ticket-admission cancellation case explicitly skips unless
the default device is GPU, requires next not called, and checks finalization
and cancelled completion. A skip is missing backend evidence, never a pass.

The inspected
[workflow](https://github.com/ml-explore/mlx-swift-lm/blob/3d066d3a0ffdc7e70c476a3d31488ea62dfdd0ac/.github/workflows/pull_request.yml#L105-L190)
contains self-hosted macOS/Xcode/MetalToolchain build and test steps. Its
FoundationModels integration SDK compile path is explicitly disabled; even
its described compile purpose would not establish runtime coverage. A workflow
definition is not proof these tests ran on the current task's host.

## Required handoff, not a blanket backend certificate

Native evidence requires separately authorized toolchain/dependency artifacts,
finite resource limits, exact API/test selection, actual device/OS/SDK, nonzero
executed test counts, skips/errors, producer ownership and actual completion
observations. There is no full CPU substitute for Metal submission, GPU stream
settlement or backgrounding behavior. A CPU-native host-control test can cover
its own stated control-flow assertion only.

Missing required Apple stack/Metal runtime remains `BLOCKED_REQUIRED_BACKEND`.
Model quality, same-input numerical equivalence, memory pressure, cached
continuation/reuse and service performance require separate evidence and frozen
acceptance gates. These tiny source tests and offline record audits do not
establish any of those outcomes or general skill efficacy.
