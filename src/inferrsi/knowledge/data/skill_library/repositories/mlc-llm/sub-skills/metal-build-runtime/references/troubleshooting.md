# Build/runtime troubleshooting

| Symptom | First check | Recovery or stop |
| --- | --- | --- |
| iPhone artifact is a dylib | Selected static tar builder and SDK | Reconcile exact target/export declaration before compiling |
| macabi uses wrong SDK or CPU ABI | macosx Metal SDK versus ios18.0-macabi host | Record both, not a single platform label |
| Explicit colon-hint prefix disappeared | Literal prefix detector | Preserve source behavior; inspect actual packaged model_lib identity |
| A Metal module exports but cannot invoke | Runnable property and registered runtime factory | Fallback serialization is not a kernel launch; require matched runtime |
| Source text is treated as metallib | Legacy callback versus explicit payload/format | Correct the actual format declaration under a separately scoped change |
| Source inspection becomes empty after loading | Source map is not serialized | Verify payload/loader/runnable behavior, not source availability alone |
| Copy/free is assumed to synchronize all work | Actual storage branch and selected/default stream | Require native ordering/lifetime evidence; flush is not wait |
| Counter/last-kernel name called per-request timing | Default-stream/global diagnostics | Do not infer attribution or speedup under concurrency |

Return exact stage, source/artifact/SDK/stream identities, observed versus
declared facts and the smallest missing native check. Do not treat a static
screen as permission to install dependencies, inspect private data or run models.
