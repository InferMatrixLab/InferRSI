# Model-runtime troubleshooting

| Symptom | Check and interpretation | Recovery/stop |
| --- | --- | --- |
| “unsupported model_type” despite Qwen branding | Native wrapper spelling is `qwen3_5_moe`, and the exact shape must match | Do not rename a dense/smaller model's field to bypass the gate; stop at incompatible architecture |
| Global Q4 config but a router is rejected | Routers/shared-expert gates require the checkpoint's Q8 packed width | Restore the compatible per-role layout; do not force all tensors to Q4 |
| A 4-bit checkpoint lacks scales/biases or loads nonsense | MLX affine uses U32 low-element-first codes with BF16 scales and additive biases per input group | Matching bits does not convert AWQ/GPTQ/GGUF/symmetric layouts. Require a verified conversion/compatible checkpoint, separately authorized |
| “checkpoint tensors were not consumed” | Unexpected names survive the explicit vision skip list | Treat as layout drift; do not broaden the skip list just to obtain a successful load |
| Config screen succeeds but native load fails | The helper does not check all required typed fields, tensor names, shapes, dtypes, payloads or tokenizer | Preserve the native error; helper output is selected-rule screening, not compatibility acceptance |
| Model fits but longer contexts or cached conversations do not | K/V allocation scales with maximum sequence per DecodeState; GDN and scratch are additional | Inventory unique buffers and retained states. Lower the supported ceiling/workload only within authorized scope; no weight-size-only estimate |
| Two views of one allocation appear identical to a weight cache | View offset was lost from binding or identity | Bind buffer+offset, preserve four-byte alignment and include offset in identity |
| Recycled state or host read produces unstable output | A pending pass may still read/write buffers, or GDN/conv reset/frontier rules were violated | Wait for GPU completion before host access/reset; preserve barriers and state position. Source reading cannot validate the repaired native path |
| Prompt plus output equals the ceiling but request is refused | Actual rendered prompt tokens plus max_tokens plus one must fit | Count actual tokenized template bytes via the supported tokenizer, retain extra slot and overflow checks |
| Non-macOS pure modules compile | GPU modules are `cfg(target_os=macos)` gated | This is not CPU inference. Missing Rust1.92, M5/macOS26, shaders or weights remains blocked, not a skip/pass |

## Support-tool and authorization boundary

The bundled screen is a narrow Python adaptation of native configuration
predicates, not a substitute Rust implementation. It accepts only the supplied
JSON and optional maximum-sequence value, reads no checkpoint payloads and
performs no native compile/import/device work. Model download commands are
excluded because they alter external storage and require separate license,
capacity and network decisions. Benchmark scripts are reference-only here:
they build/execute native engines and external MLX, outside the offline screen.
Do not repair an absent toolchain by installing a host runtime without approval.
