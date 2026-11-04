# Engine delivery template

![InferMatrix organization wordmark](engine-repo/docs/assets/infermatrix-logo.png)

Use this scaffold to deliver an InferMatrixLab inference engine with reproducible
deployment instructions, scoped evidence and a recipe for the
[recipe catalog](https://github.com/InferMatrixLab/recipe). It is maintained in
InferRSI; copying it does not make the engine depend on the InferRSI runtime.
The engine retains its own language, build system, release process and license.

## What to copy

| Source | Destination and purpose |
| --- | --- |
| [engine-repo/](engine-repo/) | Copy its **contents**, including `.github/`, into the engine repository; adapt existing files instead of overwriting them |
| [recipe.yaml](recipe.yaml) | Copy to the engine's `recipes/` directory and rename for the recipe ID |
| [branding.md](branding.md) | Shared reference; implement its attribution and asset rules in the engine |
| InferRSI evidence template | Copy the four evidence segments when opening a campaign, as described below |

Do not copy this guide or the branding guide as runtime configuration. The CI
example remains disabled until adapted and renamed. Add the engine's actual
license at its root; this scaffold does not choose one or grant rights to model
weights, logos or upstream code.

## Copy, adapt and register

1. Inspect the target's README, agent/contribution rules, license, branches and
   uncommitted changes. Record the governing task's accepted scope. Preserve its
   code and evidence; choose a repository boundary for independently maintained
   implementation, rather than creating a repository for every hardware option.
2. Copy the scaffold contents into the reviewed destination. The following Bash
   commands are **templates**; replace every angle-bracket value before use.

   ```bash
   cp -R <inferrsi-checkout>/docs/template/engine-repo/. <engine-checkout>/
   mkdir -p <engine-checkout>/recipes
   cp <inferrsi-checkout>/docs/template/recipe.yaml <engine-checkout>/recipes/<recipe-id>.yaml
   ```

3. Set the repository name and README title using the naming convention in the
   [engine README template](engine-repo/README.md). Keep its linked InferRSI
   generation attribution as the final nonempty README line. Fill in the engine
   identity, model/task, independently supported hardware combinations, source/license attribution,
   architecture, environment and real commands. Adapt both README figures using
   the visual documentation contract below. Keep only relevant folders.
   Adapt the implementation/test paths to the engine's language. Retain the
   local organization mark and provenance following [branding](branding.md); the InferRSI banner
   identifies InferRSI and is not a shared engine logo.
4. For each acceptance campaign, copy the existing
   [four-segment evidence template](../../evidence/_template/) into the engine.
   Preserve the segment names and describe the engine's own runners/validators.

   ```bash
   mkdir -p <engine-checkout>/evidence/<campaign-id>
   cp -R <inferrsi-checkout>/evidence/_template/. <engine-checkout>/evidence/<campaign-id>/
   ```

   Baseline/candidate pins, frozen gates, workload and numeric thresholds belong
   in that campaign's acceptance issue and evidence. The portable scaffold has
   no fixed campaign, hardware, metric target or acceptance revision.
5. Fill [recipe.yaml](recipe.yaml) for **one** model × engine × backend × exact
   hardware/count × precision × task combination. Give each recipe a stable ID
   and one content owner. The source belongs in the engine's recipes directory;
   use a directly maintained recipe in the catalog only when no maintainable
   engine source exists. An upstream patch recipe uses `upstream_recipe` and
   retains the upstream repository's identity.
6. Run the engine's documented lightweight checks and inspect all relative
   links after copying. Replace or remove every placeholder; search the adapted
   README, docs, recipes and workflows explicitly. Choose actual lint, build or
   CPU test commands before enabling the
   [CI example](engine-repo/.github/workflows/ci-draft.yml.example). Keep model
   downloads and hardware acceptance opt-in. InferRSI's existing four lanes are
   unchanged by this delivery template.
7. On the exact target hardware, run install, startup, minimal request and the
   required quality/E2E validation. Record the actual version, environment,
   output, date and evidence. If hardware is unavailable, keep deployment
   `unverified` and acceptance `INCONCLUSIVE`; document what remains to run.
8. Commit the engine and its source recipe, then submit the source declaration
   to the recipe repository. Its maintainers run source sync, validation, tests
   and site build, review the locked repo/path/commit and edit link, and accept
   the collection PR. Follow the catalog's
   [adding-an-engine guide](https://github.com/InferMatrixLab/recipe/blob/main/docs/adding-an-engine.md).
   Never execute source-repository scripts or recipe commands during catalog
   sync/build. Do not create a second owned copy of the same recipe ID.

   ```bash
   # In the recipe checkout, after registering the engine source:
   pnpm sync:sources
   pnpm validate
   pnpm test
   pnpm build
   ```

## README visual documentation contract

Every generated engine README embeds two local figures, not just links to a
separate design document. The reference layout is the
[MiniCPM-o 4.5 single-GPU engine](https://github.com/InferMatrixLab/minicpm-o-4.5-single-gpu-engine):
explain the engine, show its architecture, give executable setup/request steps,
then report scoped results and limitations with evidence links.

| Required figure | Included source | Adaptation and verification |
| --- | --- | --- |
| Architecture | [Editable SVG](engine-repo/docs/figures/architecture.svg) and [architecture guide](engine-repo/docs/architecture.md) | Show the engine's actual request path, modules, processes/devices, memory and outputs; verify boxes against code |
| End-to-end optimization progress | [SVG](engine-repo/docs/figures/end-to-end-optimization.svg), [example CSV](engine-repo/docs/figures/optimization-progress.example.csv) and [plot script](engine-repo/tools/plot_optimization_progress.py) | Use phase bands, labeled milestones and cumulative gain against one fixed baseline; verify each measured point against comparable E2E evidence |

![Engine architecture template](engine-repo/docs/figures/architecture.svg)

![Illustrative end-to-end optimization progress; synthetic values only](engine-repo/docs/figures/end-to-end-optimization.svg)

Both previews are **templates**. The architecture is generic; the curve uses
synthetic values and establishes no performance result. The curve's presentation
is inspired by the phase/milestone chart in
[Z.ai's inference infrastructure article](https://z.ai/blog/glm-built-its-inference-infrastructure);
its image and benchmark numbers are not copied. Follow the
[progress guide](engine-repo/docs/optimization-progress.md) to replace the sample
data, redraw the figure and retain negative/incomplete results. If measurements
are unavailable, keep an explicit illustrative or “not measured” caption.
Do not infer E2E gain by multiplying kernel speedups or mixing workloads.

These documentation tools are optional authoring dependencies, independent of
the engine runtime. Keep the figure assets local, record their
[provenance](engine-repo/docs/assets/README.md), check light/dark and narrow/wide
rendering, and preserve the README's final InferRSI attribution line.

## Recipe contract and status

The canonical contract is
[InferMatrixLab/recipe, schema version 1](https://github.com/InferMatrixLab/recipe/blob/main/schemas/recipe.schema.json).
Update that schema, its documentation and this template together when changing
the interface. For Workbench experiments, follow the
[quickstart](../quickstart.md) and [evidence template](../../evidence/_template/).

- Keep every top-level and nested key from this template. Use a snake_case task
  name and the actual backend string; backend names are not a closed enum.
- Use a real repository URL and deployment tag/commit in the engine reference.
  This identifies the implementation users deploy, independently of experiment
  baseline/candidate pins. Hardware count is a positive integer; `1` in the
  template is an illustrative value to replace with the actual count.
- `requirements`, `maintainers` and `limitations` are string lists. Maintainers
  are real GitHub logins; the update date is a real calendar date in YYYY-MM-DD.
  Formal recipes cannot contain angle-bracket placeholders, `TODO`, invented
  versions or invented maintainers.
- `commands.install`, `commands.serve` and `commands.request` must be nonempty
  reviewed text for `unverified` and `validated` entries. `benchmark` may be
  `null`. The website displays these commands; it does not execute them.
- Deployment states are `unverified`, `validated` and `unsupported`. `validated`
  requires the exact combination's evidence URL and verification date.
  `unsupported` permits null commands and requires **at least one** limitation
  explaining the confirmed blocker; the site must not offer deployment/copy
  controls for it. Unknown support remains `unverified` or a catalog inventory
  todo when required facts are missing.
- Acceptance verdicts are `PASS`, `FAIL` and `INCONCLUSIVE`. `PASS` requires the
  acceptance issue and complete evidence URLs. A deployment validation, CPU
  check or imported report alone does not establish a performance `PASS`.
  Retain the original report's authorship and exact scope; catalog registration
  is not a new hardware verification.

## Delivery checklist

- Repository name and README title follow the [engine README naming convention](engine-repo/README.md);
  its final nonempty line retains the InferRSI generation attribution and link.
- README describes supported combinations, real commands, limits, license and
  upstream sources; local assets render on both light and dark surfaces.
- README embeds the engine architecture and end-to-end optimization progress
  figures. Architecture matches code; progress data, units, baseline, milestones,
  evidence links and verdicts agree. Synthetic/unmeasured content is clearly
  labeled, including the image itself; no sample curve becomes a result claim.
- Recipe matches schema version 1 with actual identity, date, maintainer,
  deployment version and source ownership; no publishable content has placeholders.
- Evidence has `plan/`, `results/`, `patch/` and `validator/`; missing required
  quality or E2E evidence remains `INCONCLUSIVE`.
- Relevant checks and unresolved hardware validation are reported separately.
  Review records identify the reviewed revisions and distinguish self-review
  from independent review. Commits use `git commit -s` and record material agent
  contributions as required by the engine's policy.
- The recipe collection PR records source sync, validation and page checks;
  engine delivery, issue acceptance and production publication are separate steps.
