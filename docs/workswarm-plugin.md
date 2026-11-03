# InferRSI plugin for WorkSwarm (Developer Preview)

Use InferRSI from **openJiuwen JiuwenSwarm / WorkSwarm v0.2.7** to research an
inference bottleneck, prepare a comparison or inspect existing evidence. This
is the openJiuwen adapter slice of [RFC #152](https://github.com/InferMatrixLab/InferRSI/issues/152).
DSH, three-host acceptance and measured usability remain separate work.

## Download and install

From the [GitHub Releases](https://github.com/InferMatrixLab/InferRSI/releases)
page, download `inferrsi-workswarm-plugin-v<version>.zip` and `SHA256SUMS` for
the same version. Verify the archive's SHA-256 against that file. Select the
WorkSwarm archive; the Codex ZIP has a different native manifest. Release builds
stamp the native manifest and bundled runtime with the same release version.

For a local build from the InferRSI source checkout:

```text
python tools/build_workswarm_plugin.py
```

The local deliverable is `dist/workswarm-plugin.zip`. Its inspectable package
directory is `dist/workswarm-plugin/inferrsi/`. Both local and release ZIPs have
exactly one native package root:

```text
inferrsi/
  manifest.json
  tools/runtime_info_tool.py
  skills/inferrsi/SKILL.md
  skills/inferrsi/scripts/inferrsi.py
  runtime/manifest.json
  runtime/inferrsi/
  LICENSE
  README.md
```

The native manifest declares `package_type: plugin`, `id: inferrsi`, one
skill with `mode: all` and the read-only `inferrsi_runtime_info` tool. Codex
uses a different installation manifest; use the
archive built for your host. Both builders copy the same canonical runtime,
knowledge, resource notices and launcher. The source template alone is incomplete.
Choose a fresh `--output <directory>` for another build; existing outputs and
archives are never overwritten. Building does not register the plugin in a host.

In the WorkSwarm v0.2.7 web/desktop UI:

1. Open **Extensions (扩展) → My extensions (我的扩展) → Plugins (插件)**.
2. Choose **Create (创建) → Upload file (上传文件创建)** and select the WorkSwarm ZIP.
3. Confirm import and installation, then check that InferRSI is installed.
4. In a conversation in your target project, choose **+ → Extensions → Plugins**
   and select InferRSI.

The v0.2.7 dialog selects a path on the **backend service's filesystem**. For a
remote backend, transfer the ZIP there first; a browser-local file path does not
identify a remote file. Native import and installation are separate backend
operations (`plugin_packages.import_local`, then `plugin_packages.install`).
Import alone does not make a package active. Conversation selection uses
`plugin_names`; there is no package-wide enable switch in this contract.
The legacy TUI `/plugin install <path>` uses skill import and is not the native
package installation route. Public Hub publication is separate.

The bundled core needs Python 3.10+; WorkSwarm v0.2.7 itself needs Python
3.11–3.13. Select an interpreter on the execution host and keep using it.
Core knowledge operations need no InferRSI pip install. PyYAML is optional for
filesystem skill operations; image validators and target engines retain their
own dependencies. The host's model connection is still required for chat.

## First task and execution

Open your target repository and ask:

> Use InferRSI to research this engine's memory bottleneck. Cite relevant
> knowledge and prepare a comparison without starting an experiment.

Or provide an existing run and ask InferRSI to explain its verdict, missing
evidence and next action. After `skill_tool` loads the entry skill, call
`inferrsi_runtime_info({})`. Its model-facing JSON includes `success` and the
installed absolute `launcher` path. The host hides `skill_directory` from the
rendered skill result; neither that metadata nor the basename-only directory
appendix is a bootstrap path. The locator derives the path from its installed
module, accepts no arguments, writes no files and executes no command. If it
fails, reinstall/select the built native plugin rather than guessing a profile
path. The adapter keeps the target as cwd and delegates to existing research,
Collect/Read/Resource, plan/run and status/report operations. For manual diagnosis:

```text
python -X utf8 "<PLUGIN_ROOT>/skills/inferrsi/scripts/inferrsi.py" --plugin-info
python -X utf8 "<PLUGIN_ROOT>/skills/inferrsi/scripts/inferrsi.py" --help
```

`--plugin-info` reports runtime/plugin versions and the build's content identity;
it does not verify every installed file. The bundle manifest records per-file
SHA-256 values. A missing runtime has a reinstall/build repair path. Knowledge
reads retain their qualified identity, exact revision and attribution; stale
revisions are rejected rather than silently replaced.

`plan` previews a specification and starts no experiment. Freeze validators and
accepted gates before candidate search. Installation grants no new experiment
authority. Use the existing local executor on a prepared target; the adapter
does not install engines, download weights or dispatch SSH jobs.

For swarm work, designate one execution owner for a comparison. Other agents
must not duplicate its runs, edit measured sources/frozen validators or contend
for allocated devices. Carry workspace, interpreter, selected revisions and
existing process/run identities across a handoff. A RunSpec snapshot is not a
distributed device lease.

Keep execution attached to the host's process tool. Cancellation must reach
that process and its cleanup path. After a timeout, disconnect or reconnect,
inspect process state and existing evidence before another invocation; never
silently retry. Existing-run inspection does not resume execution. Preserve
PASS / FAIL / INCONCLUSIVE and distinguish synthetic integration checks from
model-quality or service-performance evidence.

## Update, stop selecting and uninstall

Deselect InferRSI in the conversation selector to stop selecting it. Start a
new conversation if its prior instructions are already in context; deselection
does not erase messages or stop an existing process.

For updates, finish or inspect owned work, deselect and uninstall the old
package, then import/install the fresh ZIP and select it in a new conversation.
Duplicate package IDs are rejected; do not bypass the host registry. Use the
native uninstall action to remove the package. Keep experiment evidence outside
the package directory. Uninstall does not cancel an owned run or delete evidence
in target directories. The adapter adds no service, hook or scheduler.

## Compatibility and verification

The native contract is based on the released **v0.2.7** host, rather than an
assumed universal openJiuwen SDK/plugin format:

- [Manifest specification](https://github.com/openJiuwen-ai/jiuwenswarm/blob/v0.2.7/jiuwenswarm/resources/agent/workspace/skills/plugin-creator/references/manifest-spec.md)
- [Import/install lifecycle](https://github.com/openJiuwen-ai/jiuwenswarm/blob/v0.2.7/jiuwenswarm/server/runtime/extension_package_manager.py)
- [UI import/install flow](https://github.com/openJiuwen-ai/jiuwenswarm/blob/v0.2.7/jiuwenswarm/channels/web/frontend/src/stores/pluginPackageStore.ts)

Run the host's validator in its prepared environment against the built package:

```text
python -X utf8 "<HOST_SOURCE>/jiuwenswarm/resources/agent/workspace/skills/plugin-creator/scripts/validate_plugin.py" "<BUILT_PACKAGE>"
```

`--no-hot-load` checks only structure/quality. A skipped hot-load layer does not
establish actual loading. The host validator's L0/L1/L2 labels refer to plugin
validation, independently of InferRSI's campaign validation ladder.

For the native backend lifecycle, use the host's prepared interpreter from a
scratch directory outside either checkout:

```text
python -X utf8 "<INFERRSI_SOURCE>/tests/check_workswarm_installed.py" --host-source "<HOST_SOURCE>" --archive "<BUILT_ZIP>"
```

This check creates its own temporary profile, imports and installs the archive,
checks selected/empty conversation metadata and the installed launcher, then
uninstalls and reinstalls it. It verifies installed runtime hashes, exact reads,
stale-revision rejection, and preservation of an unrelated registry entry and
existing evidence. A real `DeepAgent` loads the native package and dispatches
`skill_tool` followed by `inferrsi_runtime_info` through `AbilityManager.execute`.
The launcher is parsed only from the resulting model-facing `ToolMessage` and
then invoked from an external target workspace. Structured path metadata is
discarded. Extension unload is also checked. The probe runs in a disposable
subprocess so its SDK log handles close before the parent removes the temporary
profile. The replay invokes no model and does not change the desktop user's profile.

Windows v0.2.7's importer stages and copies the entire package under its data
root. The canonical knowledge tree contains deep paths, so native import may
fail with `WinError 206` / `WinError 3` when the host process does not support
extended-length paths. The builder's Windows path support does not repair the
host's later copy. An isolated backend can be checked with a process-local
extended-length absolute `JIUWENSWARM_DATA_DIR`; this is not proof that an
existing desktop instance uses that spelling. Do not relocate user data or
change global Windows policy merely to test a package.

Validation on **2026-11-03, Windows / Python 3.12**:

| Check | Observed scope |
| --- | --- |
| Official v0.2.7 validator | Quality, static checks and real hot-load passed with zero errors/warnings; one skill and one read-only locator bound |
| Native backend lifecycle | Two import/install/uninstall cycles completed using an extended-length isolated data root; reinstall, selection metadata and unrelated registry/evidence preservation checked |
| Model-facing bootstrap | Native skill discovery and locator ToolMessages resolve the installed launcher; isolated CLI invocation, unknown-argument rejection and extension unload checked without calling a model |
| Extracted runtime | Both host distributions exercise canonical bytes/notices, isolated exact knowledge reads, stale-revision rejection, optional dependency guidance, preview without execution and synthetic CPU run/status/report for all three verdicts |
| Desktop UI, LLM dispatch, cancellation/reconnect | Not exercised |

Plain unbuilt source reports runtime version `0+unknown`; `--plugin-info`
reports that development state explicitly. A versioned build can use
`--release-version <version>` only when the already-built runtime agrees;
this stamps generated host metadata without modifying canonical source bytes.

Actual desktop/LLM journeys,
cancellation/reconnect, other host releases and Linux/macOS installation require
their own verification. Packaging or hot-load success alone does not complete
the RFC or demonstrate a usability improvement.
