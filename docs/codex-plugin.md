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

If your Codex client offers **Plugins → Add → Upload plugin archive**, use it
to import the downloaded `inferrsi-codex-plugin-vX.Y.Z.zip`. If the InferRSI
detail page offers **Install plugin**, select it and follow the prompts. After
installation, enable InferRSI, open your target repository and start a new
conversation.

[Watch or download the installation guide (English narration and subtitles)](https://raw.githubusercontent.com/InferMatrixLab/InferRSI/main/docs/assets/inferrsi-codex-install-en.mp4).
The video uses English UI illustrations based on the supplied screenshots to show
the menu click order; it does not record a completed upload or installation.
Exact labels and availability depend
on the client and workspace permissions. Here, offline package describes the
included runtime and resources; it does not guarantee offline client operation.

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

## MindIE knowledge

The agent assesses each question independently and consults MindIE only when
the answer needs evidence about Ascend hardware or software, such as CANN,
torch_npu, vllm-ascend, Ascend Triton or SoC behavior. This includes research,
diagnosis, planning, implementation, review and knowledge-only conversations.
Generic framework questions use the usual sources; a search miss or an earlier
Ascend topic does not make them eligible for MindIE. Mixed questions use MindIE
only for their Ascend-dependent part, when existing evidence is insufficient.
Answers cite the delivered versioned material and its applicability limits;
candidate and campaign association applies when the task includes that work.

### Supported versions

The project reader supports Python 3.10+ and a synced local catalog from
`mindie-knowledge 0.13.13`. The query and explain results follow the graded
[MindIE Codex v0.1.21 contract](https://github.com/mindie-agent/mindie-agent-codex/blob/v0.1.21/plugins/mindie-agent/skills/mindie-agent/references/domain-skills.md).

### Enable and revoke

With InferRSI installed, approve a synced domain once from the target checkout.

```sh
inferrsi mindie enable --domain operators
inferrsi mindie describe
```

New sessions in that checkout reuse the grant. Use `--adapter-config <path>`
when the MindIE adapter is installed outside its default location. Run
`inferrsi mindie disable` from the same checkout to revoke the grant.

### MCP configuration and queries

Add the following entry to the trusted checkout's `.codex/config.toml`.

```toml
[mcp_servers.inferrsi_mindie]
command = "<absolute-inferrsi-executable>"
args = ["mindie", "serve"]
cwd = "<absolute-project-checkout>"
enabled_tools = ["knowledge_query", "knowledge_explain"]
```

For the plugin ZIP, set `command` to the Python executable and prepend the
absolute bundled launcher path to `args`.

Call `knowledge_query` with a `query` and observed `conditions`. Pass relevant
versioned `ref` values as `refs` to `knowledge_explain` and read the returned
`units` and `requires`. The same reads are available through the CLI.

```sh
inferrsi mindie query --input query.json
inferrsi mindie explain --input explain.json
```

The reader automatically stores receipts under
`~/.config/inferrsi/mindie-projects/reads/<project-hash>/` and returns
`receipt_directory` on success. Stored receipts contain `input.json` and
`receipt.json`, plus `result.json` when a response was received. Keep these
receipts outside the source checkout; the caller does not select their location.
Recorded read failures report their receipt path in the error message.

### Associate reads with a candidate

Use the `receipt_directory` from each call. Import the `input.json` and
`result.json` files with the exit codes in `receipt.json` into an existing
campaign or one created with `campaign init`.

```sh
inferrsi campaign import-mindie --directory "$CAMPAIGN_DIR" --id "$READ_ID" \
  --query-input "$QUERY_READ/input.json" --query-result "$QUERY_READ/result.json" \
  --explain-input "$EXPLAIN_READ/input.json" --explain-result "$EXPLAIN_READ/result.json" \
  --query-exit-code "$QUERY_EXIT" --explain-exit-code "$EXPLAIN_EXIT"
```

Use the exported `context.json` and `reviewed-context.txt` with the
[candidate trace template](https://github.com/InferMatrixLab/InferRSI/blob/main/docs/dashboard.md#per-candidate-narrative-schema-version-1).
Record which versioned source informed the code change. Set
`reviewed_by_caller: true` after reviewing the trace and the retained reads.
Use `campaign assemble-trace` and `campaign record` to bind it to the frozen
candidate, round, and independent evaluation `run_id`.

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
requires that version to match the generated runtime. It stamps the generated
plugin manifest and pins the bundled README's video link to the release tag.
The tracked source template remains unchanged.
Unbuilt source previews use the runtime's explicit `0+unknown` fallback.

Only the ZIP is attached to Releases. The raw `plugins/inferrsi/` source template
does not contain the bundled runtime and is not an installation package.

The build copies the canonical Python package, its packaged knowledge/resources
and source notices, plus the repository license. It records per-file SHA-256
digests and the runtime version in `runtime/manifest.json`. Generated copies live
only in the distribution; maintain procedures and metadata in their existing
source owners. No new core dependencies or CI lanes are introduced.

## Updates, disable and uninstall

Download and verify the new Release ZIP, then use the client's supported update
or replacement flow for the existing InferRSI plugin. Check the selected bundle with
`--plugin-info` in a new conversation. Do not overwrite an installed cache or
carry forward an old runtime by hand.

For older installations managed through Plugin Creator, file updates overlay
existing files. Compare the old and new runtime manifests and explicitly remove
obsolete runtime files and resources while retaining the same plugin identity
and audience. Files omitted from that update archive remain installed. Verify
how native ZIP replacement behaves on your target client.

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
