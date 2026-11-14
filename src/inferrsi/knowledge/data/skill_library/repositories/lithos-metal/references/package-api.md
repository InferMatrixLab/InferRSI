# Package and API contract

Use for installation planning and for distinguishing software inspection from
accelerator/model verification. Facts below are from the pinned source readset;
selected API signatures and CLI help were also inspected in an installed 0.1.2.

## Installation and dependencies

The distribution and public command are `lithos-metal`; imports use `monolith`.
`pyproject.toml` declares Python >=3.10 and NumPy >=1.26. The source build/release
instructions use Python 3.12 and Xcode Command Line Tools. These are distinct
claims: metadata acceptance of a Python version is not a tested native build.
The source build uses CMake and nanobind on Darwin and packages the Metal kernel
sources. A non-Darwin package install omits the native extension.

Select an already provisioned environment or a private environment suited to the
requested scope. An explicit install, when authorized, can use:

```bash
python -m pip install 'lithos-metal==0.1.2'
python -c 'import monolith; print(monolith.__version__)'
```

Installing a package can access the package index and build native code. It is
separate from running the no-download diagnostic. Availability of a compatible
prebuilt distribution must be checked in the chosen environment. The upstream
alternative is the public Homebrew tap; it is not needed to read this skill.

| Scope | Declared dependency surface | What it can establish |
| --- | --- | --- |
| Core package | NumPy | Imports, IR/layout/program/pack/cache Python contracts |
| `dev` extra | pytest | Source contract tests with tiny fixtures |
| `serve` extra | FastAPI, Pydantic, Uvicorn, Transformers, safetensors, huggingface_hub, Jinja2 | HTTP adapter and model/tokenizer loading surfaces; model startup still requires assets and Metal |
| `oracle` extra | Torch, Transformers, safetensors, huggingface_hub | Reference comparisons, not automatic golden/model availability |

FastAPI TestClient tests additionally need `httpx`; it is not a listed `serve`
dependency at this pin. Do not install all extras merely to inspect the package.
Apple silicon/macOS 26+ and a matching registered backend are the documented
runtime scope. Native module import and a tiny shader are separate checks;
neither proves a specific target/draft recipe runs correctly.

## Public call boundaries

| Entry | Relevant parameters and defaults at 0.1.2 | Contract |
| --- | --- | --- |
| `monolith.generate.load_session(model_dir, pack_dir, *, max_context=4096, drafter_dir=None, drafter_pack=None, drafter_kind='dspark', **options)` | Local checkpoint and prepared pack inputs; target/draft config resolved by model packages | Constructs `Session`; it is not the serving checkpoint downloader |
| `monolith.generate.Session(...)` | `verify='cost'`, `verify_length=None`, `draft_sampling='argmax'`, `barriers='minimal'`, `commute_norm=True`, `fast_math=False`, `prefix_cache=False` | Lower-level policy; serving overrides several choices |
| `Session.generate(prompt_ids, max_new_tokens, *, steps_per_cb=8, in_flight=3, on_tokens=None, cancelled=None, cache_prefix_tokens=0)` | Nonempty integer prompt IDs; callback receives cumulative tokens | Handles prefill, cache restore, decoder transition and bounded host pumps |
| `monolith.compiler.compile_program(...)` | `dynamic_t=False`, `drafter=None`, `barriers='minimal'`, `commute_norm=True` | Speculation requires dynamic T, compatible layout bounds and a draft pack |
| `monolith.runtime.Engine(program, device=None, buffers=None, fast_math=False, pipeline_cache=None)` | Allocates/maps buffers and encodes ICB; constructor creates a device if absent | Requires actual native runtime; inspection need not construct it |
| `StepStateLayout(t_max=8, gamma_max=7)` | Requires `t_max >= gamma_max + 1 >= 1` | Shared binary layout, not a model capacity or recipe guarantee |
| `PrefixCache(entries, max_bytes=4*1024**3, min_tokens=0, store=None)` | Host snapshots, optional disk store | Saves declared model/drafter state; scratch and worker counters are excluded |

Do not copy the illustrative defaults into campaign thresholds. `Session`'s
cost policy is not the server default: `ServingAssets.options` selects fixed
verification for its DSpark path. Read the relevant subskill before choosing.

## Safe software inspection

The bundled helper accepts `--expected-version VERSION` (default `0.1.2`) and
`--check-contract`. Output is JSON with version agreement, API parameter names,
optional-module discovery and, if requested, CPU layout/barrier assertions.
Exit 0 means those checks completed; exit 1 means a required import, version or
contract check failed. It omits installation paths and exception text. It does
not report overall backend readiness and never substitutes for Metal/model tests.

CLI `--version` and `serve --help` are parser checks. `serve --model HUB_ID` may
download target and automatic draft checkpoints, prepare large packs, compile
and warm up. Use the local-only recipe in the serving route only when a server
run is separately within scope.
