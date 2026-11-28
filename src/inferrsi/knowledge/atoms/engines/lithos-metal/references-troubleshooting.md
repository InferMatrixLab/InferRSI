# Cross-route troubleshooting

Use before diagnosing a kernel or modifying stored state.

| Symptom | Discriminating check | Recovery or stop condition |
| --- | --- | --- |
| `No module named lithos_metal` | Distribution is `lithos-metal`; namespace is `monolith` | Use the documented imports. Run the bundled software diagnostic in the selected installed environment. |
| Import works, generation does not | Separate native-extension import, device creation, shader compilation, registered chip/config match and model assets | Inspect the actual failed boundary. A CPU-only install is useful for contract inspection but is not a generation backend. |
| Source build fails | Compare interpreter/toolchain to the source Python 3.12/Command Line Tools instructions and Darwin build dependencies | Preserve the build error. Missing `xcrun metal` alone does not prove runtime shader compilation unavailable; test the actual native boundary separately when authorized. |
| `serve` import or TestClient fails | `serve` extra versus separately required `httpx` in tests | Install only the scoped missing dependencies in an appropriate environment. No model weights are required for mocked HTTP tests. |
| Package/version differs from this guide | Helper version/API report and pinned source readset | Treat as drift; inspect changed signatures and source before using old recipe advice. |
| `No registered backend` or backend/device mismatch | Chip name, Apple family and core count all participate | Do not rename/copy another chip's profile. Use a real matching backend or stop qualification. |
| Apparent huge throughput gain | Identify measured interval and counted committed tokens | Target-only compute excludes drafting, acceptance/rewind, prefill and HTTP overhead. Require complete workload evidence for service wording. |
| State wrong only after session/recipe change | Route compiler geometry, generation commit and serving adoption together | Compare compatible state names/size/layout, identical weight windows and exact-prefix identity. Recompilation or a pipeline hit alone does not reset sequence state. |

Keep reproducible observations separate from hypotheses. A source contract
assertion supports that contract at the pin; it cannot attribute an unseen
production failure or certify all backends. Reports should identify source,
software/CPU, synthetic Metal and model/E2E coverage individually.
