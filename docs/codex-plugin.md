# InferRSI plugin for Codex (Developer Preview)

Use InferRSI from a Codex conversation in your target repository: research a
bottleneck, prepare a comparison, or inspect an existing run. This is the Codex
implementation slice of [RFC #152](https://github.com/InferMatrixLab/InferRSI/issues/152);
DSH/openJiuwen integration and a measured usability comparison remain separate.

## Install from the Release ZIP

The [daily release guide](https://github.com/InferMatrixLab/InferRSI/blob/main/docs/releases.md)
describes the versioned installer named
`inferrsi-codex-plugin-vX.Y.Z.zip` in
[GitHub Releases](https://github.com/InferMatrixLab/InferRSI/releases). Download
it with `SHA256SUMS` and verify the ZIP's SHA-256 before importing it. The ZIP
contains exactly one plugin directory:

```text
inferrsi/
  plugin.json
  skills/inferrsi/SKILL.md
  skills/inferrsi/scripts/inferrsi.py
  runtime/manifest.json
  runtime/inferrsi/
  LICENSE
  README.md
```

The downloaded archive bundles the same-version InferRSI runtime and knowledge;
installation requires no source checkout, package build or separate pip install.
There is no marketplace catalog, registration step or distribution branch.

In a Codex client with **Plugin Creator** available, provide the downloaded ZIP
and ask: "Import this InferRSI plugin ZIP as a private plugin." For an existing
InferRSI plugin, ask to update that plugin from the ZIP instead of creating a
duplicate. Use the returned plugin link to enable it, then start a new
conversation. The import uploads the archive to the account/workspace; it still
requires a network connection. Here, offline package means the runtime and
resources are included, not that the Codex client can operate air-gapped.

Clients without archive import cannot install this package directly. The current
Codex CLI's `plugin add` accepts marketplace selectors, not ZIP paths; do not pass
the archive to that command. Archive ingestion and enablement must be verified
on the target host; release checks validate package contents and local execution.

Requires a local Codex client with plugin support and Python 3.10 or newer.
Git is needed for target-repository inspection and experiment source provenance.
The built plugin contains the same InferRSI core and knowledge bytes as its
source build; basic operations need no pip install, network service or API key
specific to InferRSI. Your normal Codex model connection is still required.

## First task

Open the repository you want to investigate and ask, for example:

> Use InferRSI to research this engine's memory bottleneck. Find relevant
> knowledge and explain what is needed for a controlled comparison.

Or:

> Use InferRSI to inspect the existing run I provide and explain its verdict,
> missing evidence and next action.

The plugin checks its bundle/interpreter, reads relevant knowledge progressively,
and uses the current CLI's help to prepare operations. Its optional onboarding
action invokes the same entry skill. Setup does not start benchmarks.

Use the script resolved from the installed skill for manual diagnosis:

```text
python -X utf8 "<PLUGIN_ROOT>/skills/inferrsi/scripts/inferrsi.py" --plugin-info
python -X utf8 "<PLUGIN_ROOT>/skills/inferrsi/scripts/inferrsi.py" --help
```

Core `knowledge`, packaged `collect/read`, `doctor`, `plan/run` and
`status/report` delegate to the bundled runtime. The optional `skills` commands
and checkout-skill sources need PyYAML in the selected Python interpreter.
Image validators and target engines retain their own optional dependencies.

## Build from the InferRSI source checkout

```text
python tools/build_codex_plugin.py
```

This writes a fresh `dist/codex-plugin/` standalone plugin directory and
`dist/codex-plugin.zip`. The ZIP always has the single enclosing `inferrsi/`
directory shown above; the output directory's name does not add a wrapper.
To rebuild, choose a new `--output <directory>`; the builder refuses to replace
an existing distribution/archive.

For release builds, first build the runtime so SCM generates `_version.py`, then
pass `--release-version <version>` and a versioned output directory. The builder
requires that version to match the generated runtime, and stamps only the
generated plugin manifest. The tracked source template remains unchanged.
Unbuilt source previews use the runtime's explicit `0+unknown` fallback.

Only the ZIP is attached to Releases. The raw `plugins/inferrsi/` source template
does not contain the bundled runtime and is not an installation package.

The build copies the canonical Python package, its packaged knowledge/resources
and source notices, plus the repository license. It records per-file SHA-256
digests and the runtime version in `runtime/manifest.json`. Generated copies live
only in the distribution; maintain procedures and metadata in their existing
source owners. No new core dependencies or CI lanes are introduced.

## Updates, disable and uninstall

Download and verify the new Release ZIP, then ask Plugin Creator to update the
existing InferRSI plugin from that archive. Check the selected bundle with
`--plugin-info` in a new conversation. Do not overwrite an installed cache or
carry forward an old runtime by hand.

Plugin Creator updates overlay existing files. Ask it to compare the old and new
runtime manifests and explicitly delete removed runtime/resources while retaining
the same plugin identity and audience; omitting a file from the ZIP alone does
not remove its installed copy.

Disable InferRSI in the desktop plugin UI when you want to retain its installation
but stop loading it. To uninstall, remove the selected InferRSI plugin in the
client's plugin management UI. Existing marketplace-based previews are a separate
installation: disable/remove them in the client before enabling the ZIP import
so only one InferRSI entry skill is active.

Removal does not delete target repositories or experiment evidence. The plugin
registers no MCP server, hooks, daemon or scheduled task.

## Troubleshooting and limits

| Observation | Next step |
| --- | --- |
| Python cannot be found or is too old | Select/install Python 3.10+ and use its executable consistently |
| Incomplete bundle or version mismatch | Rebuild/reinstall the distribution; do not substitute an unrelated installed runtime |
| Optional skills dependency missing | Use packaged Collect/Read, or install PyYAML in the chosen interpreter |
| No knowledge match | Inspect the query/source selection; no match does not establish lack of an optimization |
| Target backend unavailable | Fix the target environment; knowledge research remains usable |
| Interrupted experiment | Inspect its existing status/evidence before deciding on a new run |

Execution remains local to the prepared target machine. The plugin does not
install accelerator stacks, download weights or dispatch SSH jobs. A `plan`
preview does not freeze validators or authorize execution. Preserve the user's
accepted campaign gates, evidence and authorization; completed processes do not
automatically establish PASS.

The preview's functional checks and actual host observations must be reported
separately from a usability pilot or an inference-performance campaign. Synthetic
CPU comparisons establish command/evidence wiring only.

Plugin installation and packaging follow the
[official OpenAI plugin guide](https://developers.openai.com/plugins/build/plugins).
