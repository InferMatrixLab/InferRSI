# Platform/configuration troubleshooting

| Signal | Likely contract | Bounded next step / stop condition |
| --- | --- | --- |
| Root import succeeds but platform is not Metal | Lazy package versus actual vLLM entrypoint/availability | Inspect installed distribution entrypoints and OS/backend identity; do not label root import as registration success |
| `Invalid vllm-metal environment` with multiple fields | Startup parser aggregates invalid values | Run selected-knob helper on a synthetic explicit plan, repair every named field, then restart the authorized worker; never dump all environment variables |
| Switch unexpectedly disabled | Only literal`1` enables; explicit values override defaults | Replace intended true with`1`; `yes` remains false by design |
| Native symbol/MLX version/stale artifact error | Exact MLX/header/extension/shader ABI drift | Stop; inspect installed runtime and loaded artifact/build identities. Rebuild only with authorized Xcode/tools and restart, not by suppressing stale checks |
| Source installation lacks GPU kernels | Editable Python install is not native build | Return BLOCKED_REQUIRED_BACKEND without compatible Mac/SDK/artifacts; CPU imports do not repair this |
| V2 runner rejected on MLX | Wrong backend-runner pairing | Use intended MLX V1 or separately qualify MPS; do not force V2 to bypass validation |
| Unexpected text-only model | Effective auto/format/vision guard | Check mode, checkpoint format, scales, processor and vision weights. Stable identities before restart; text output does not validate vision |
| API/worker backbone drift | Inputs changed between processes | Stop/restart with immutable checkpoint/mode; do not manually mutate only worker state |
| User asks to run installer/lint/test shell scripts | Scripts can install dev tools, download toolchains and build artifacts | Inspect effects first; safe helper checks are not permission for host mutation |

The current knowledge delivery has installed selected pure API inspection but
not a healthy inference dependency set. Missing MLX/vLLM/native operators,
dependency conflicts or unsupported host tags remain real limitations, never
successful skips. Native MPS, MLX model loading and kernel execution require
their own actual backend evidence.
