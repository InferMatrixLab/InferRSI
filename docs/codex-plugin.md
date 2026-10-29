# InferRSI plugin for Codex (local preview)

Use InferRSI from a Codex conversation in your target repository: research a
bottleneck, prepare a comparison, or inspect an existing run. This is the Codex
implementation slice of [RFC #152](https://github.com/InferMatrixLab/InferRSI/issues/152);
DSH/openJiuwen integration and a measured usability comparison remain separate.

## Install from the GitHub preview

Give Codex the [preview installation page](https://github.com/zengchuang-hw/OmniRSI/tree/codex/inferrsi-plugin-preview)
and ask it to install InferRSI. On Windows, use the following PowerShell route
to fetch only the generated branch and enable long paths for this Git operation:

```powershell
$pluginInstallDir = Join-Path $env:LOCALAPPDATA "InferRSI/codex-plugin-preview"
git -c core.longpaths=true clone --depth 1 --single-branch --branch codex/inferrsi-plugin-preview https://github.com/zengchuang-hw/OmniRSI $pluginInstallDir
codex plugin marketplace add $pluginInstallDir
codex plugin add inferrsi@inferrsi-preview
codex plugin list --marketplace inferrsi-preview --json
```

Choose a fresh directory, or inspect an existing installation before reusing it.
This does not change global Git configuration. Direct Git marketplace registration
on the tested Windows client first checked out the repository's default branch
and hit the platform's path-length limit; the explicit single-branch clone avoids
that unrelated checkout. Other clients may use the native Git-source route:

```text
codex plugin marketplace add https://github.com/zengchuang-hw/OmniRSI --ref codex/inferrsi-plugin-preview
codex plugin add inferrsi@inferrsi-preview
codex plugin list --marketplace inferrsi-preview --json
```

This uses a generated preview branch in the fork, separate from InferRSI's main
branch and the public plugin directory. The branch includes the marketplace,
native plugin and bundled runtime, so the client does not need to build source.
Keep one InferRSI installation active: if switching from the older local preview,
remove `inferrsi@inferrsi-local` and its marketplace using the commands below.
Start a new conversation after installation; refresh/restart a desktop client
if its plugin catalog has not updated. Both installation routes require a local
Codex client with plugin support, Python 3.10+ and Git.

## Install from a local archive

The [daily release](releases.md) includes a versioned installer named
`inferrsi-codex-plugin-vX.Y.Z.zip` in
[GitHub Releases](https://github.com/InferMatrixLab/InferRSI/releases). Download
it with `SHA256SUMS`, verify the checksum and extract it into a fresh directory.
The enclosed `inferrsi-codex-plugin-vX.Y.Z/` directory is the marketplace root;
its marketplace name is `inferrsi-local`. This installer bundles the same-version
InferRSI runtime and knowledge, so it does not need a separate pip installation.

Requires a local Codex client with plugin support and Python 3.10 or newer.
Git is needed for target-repository inspection and experiment source provenance.
The built plugin contains the same InferRSI core and knowledge bytes as its
source build; basic operations need no pip install, network service or API key
specific to InferRSI. Your normal Codex model connection is still required.

Obtain the generated marketplace folder, or extract its ZIP. Then run:

The following selectors are for the default `inferrsi-local` build. For an
archive from the GitHub preview, use `inferrsi-preview` instead; the authoritative
name is the top-level `name` in `.agents/plugins/marketplace.json`.

```text
codex plugin marketplace add "<MARKETPLACE_ROOT>"
codex plugin add inferrsi@inferrsi-local
codex plugin list --marketplace inferrsi-local --json
```

`<MARKETPLACE_ROOT>` is the extracted directory containing
`.agents/plugins/marketplace.json` and `plugins/inferrsi/`. Substitute its actual
path. Local marketplace paths are resolved from that root. The raw
`plugins/inferrsi/` source template is not a complete distribution.

In desktop clients, the same local marketplace can be found in the plugin
directory and InferRSI installed/enabled there. Begin a new conversation after
installation so its skill catalog includes InferRSI. If a running client does not
refresh the marketplace, restart it and check again.

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

This writes a fresh `dist/codex-plugin/` marketplace and
`dist/codex-plugin.zip`. Use that marketplace directory in the install commands.
To rebuild, choose a new `--output <directory>`; the builder refuses to replace
an existing distribution/archive.

For release builds, first build the runtime so SCM generates `_version.py`, then
pass `--release-version <version>` and a versioned output directory. The builder
requires that version to match the generated runtime, and stamps only the
generated plugin manifest. The tracked source template remains unchanged.
Unbuilt source previews use the runtime's explicit `0+unknown` fallback.

For a separately named distribution, use `--marketplace-name inferrsi-preview`.
Publish only the generated marketplace directory on its distribution branch;
the source template alone is not a working remote plugin.

The build copies the canonical Python package, its packaged knowledge/resources
and source notices, plus the repository license. It records per-file SHA-256
digests and the runtime version in `runtime/manifest.json`. Generated copies live
only in the distribution; maintain procedures and metadata in their existing
source owners. No new core dependencies or CI lanes are introduced.

## Updates, disable and uninstall

Build a fresh distribution. Remove this preview plugin and its marketplace using
the commands below, then repeat installation with the new marketplace root.
Check the selected bundle with `--plugin-info` in a new conversation. This also
refreshes a locally rebuilt preview with the same version. Do not overwrite an
installed cache or carry forward an old runtime by hand.

Disable InferRSI in the desktop plugin UI when you want to retain its installation
but stop loading it. To remove the preview:

```text
codex plugin remove inferrsi@inferrsi-local
codex plugin marketplace remove inferrsi-local
```

For the GitHub preview, substitute `inferrsi@inferrsi-preview` and
`inferrsi-preview` respectively. With the Windows clone route, update only that
clone using `git -C "<install-directory>" -c core.longpaths=true pull --ff-only`,
then reinstall and verify the plugin. A source registered directly as Git can
instead be refreshed with `codex plugin marketplace upgrade inferrsi-preview`.
Refresh/reinstall the selected bundle, especially when a preview is rebuilt with
the same version.

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
