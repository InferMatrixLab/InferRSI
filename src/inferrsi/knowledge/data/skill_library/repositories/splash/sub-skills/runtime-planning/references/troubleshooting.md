# Runtime-planning troubleshooting

| Symptom | Discriminating check | Recovery and stop |
| --- | --- | --- |
| Process RSS exceeds `--max-memory` | Separate Metal/device footprint, charged PLE host cache, other host objects and process accounting | The flag is not combined RSS; reduce the engine ceiling to leave room for other apps. Do not claim an allocator leak from the difference alone |
| A higher `--max-memory` does not raise usable capacity | Compare the configured value with the automatic recommended-working-set-minus-margin ceiling | The user cap can only lower it. Do not raise OS limits or bypass native guards |
| `off` makes PLE/expert memory much larger | Check the effective setting and target format | `off` means load the entire corresponding part, not disable its weights. Prefer auto or an explicit legal store only if the selected format supports streaming |
| `--ple-memory SIZE` is refused on a nominally small GGUF | Check whether its table layout is rebuilt NVFP4 or rotated, and the row-store minimum | Those layouts load the table whole; another numeric size does not make them streamable. Stop or choose a separately authorized compatible model |
| Floors exceed budget before a request runs | Read fixed weights, draft/vision, arenas, staging/ANE, one state, KV runway and minimum stores | Lower context/optional footprint only with a valid plan, or use suitable hardware/model. Do not remove the smallest-store or KV-runway check |
| Memory plan succeeds but requests wait | Distinguish engine-budget headroom from host pressure, live reservations and transfers awaiting a command-free reclaim point | Inspect wait/refusal reason and actual pressure. A static plan is not a promise of immediate allocation |
| Large context changes with disk space | Inspect supported spill capability and `context_bounds.bound`, disk quota and active-KV room | Preserve disk as part of the execution contract; a disk tier is not unlimited RAM. Do not generalize spill behavior to dense/no-tier paths |
| Model-check accepts but load fails | Distinguish screened configuration/header from full tensor shape and payload checks | Retain the native error and exact file identity. Do not reclassify metadata acceptance as model qualification |
| Mixed BF16 tensors load but an all-BF16 GGUF is refused | Determine whether every loaded projection/expert is unquantized | A legal tensor role/type does not imply a legal entire target. Select a compatible quantized variant only under download authority |
| Changing BF16 state changes output despite FP32 compute | Freeze prefill chunk, capture/replay boundaries, state format and sampling | BF16 storage introduces boundary rounding; compare quality on the actual target and preserve cache format separation |
| Parser accepts `2.5G`, but an engine refuses it | Syntax parsing has no model geometry or device measurement | Inspect native minimum and actual plan; helper success never proves fit |
| `1.5`, `.5G`, `0G` or `off` for sparse-KV is rejected | Run the offline helper with the matching `--kind` | Byte fractions require digits before/after the decimal and a suffix; zero/off differ by option. Do not silently normalize ambiguous intent |

## Support-tool boundary

`scripts/parse_budget.py` is a narrow, stdlib-only adaptation of selected
`server/serve_options.py` parsing logic. It gives normalized syntax only and
does not import Splash or need the original checkout. Installer/model scripts
remain reference-only because they couple engine checks, external Hub access,
large weight writes and selection state; reproducing them here would turn an
offline knowledge helper into an unapproved installer. Native plan/governor/
audit tests and actual Metal/ANE/model measurements remain separate checks.
