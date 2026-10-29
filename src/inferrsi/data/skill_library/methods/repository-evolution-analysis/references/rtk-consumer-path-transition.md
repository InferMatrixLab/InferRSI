# Worked transition: manager discovery is not consumer reachability

Status: source-derived **candidate**; empirical validation **not_run**. This is
one learning example inside repository-evolution-analysis, not a new skill,
benchmark task or independent heldout task. It does not establish automatic
learning, agent efficacy or Magpie's development speed.

## Source boundary

The inspected change is
[`9848a9062a65c49e074c09770dc7de73dd012bea`](https://github.com/yetone/magpie/commit/9848a9062a65c49e074c09770dc7de73dd012bea),
whose recorded parent is
[`4b5d6d725fae3d8a263f6e43c707400e3765b84f`](https://github.com/yetone/magpie/tree/4b5d6d725fae3d8a263f6e43c707400e3765b84f).
Public source was inspected on 2026-10-29; upstream programs, shell profiles,
installers, Go tests and browser tests were **not executed** for this example.
The commit's reported checks are author reports, not local receipts.

| Readset | Parent evidence | Change evidence and purpose |
| --- | --- | --- |
| Discovery and diagnostic view | [`internal/library/rtk.go`](https://github.com/yetone/magpie/blob/4b5d6d725fae3d8a263f6e43c707400e3765b84f/internal/library/rtk.go) | [`rtk.go`](https://github.com/yetone/magpie/blob/9848a9062a65c49e074c09770dc7de73dd012bea/internal/library/rtk.go): `rtkPath`, `ReadRTK`, hook-state detection |
| PATH observation and mutation | No `rtk_path*` files in this parent-to-change diff | [`rtk_path.go`](https://github.com/yetone/magpie/blob/9848a9062a65c49e074c09770dc7de73dd012bea/internal/library/rtk_path.go), [`rtk_path_other.go`](https://github.com/yetone/magpie/blob/9848a9062a65c49e074c09770dc7de73dd012bea/internal/library/rtk_path_other.go), [`rtk_path_windows.go`](https://github.com/yetone/magpie/blob/9848a9062a65c49e074c09770dc7de73dd012bea/internal/library/rtk_path_windows.go) |
| PATH supplied to the observer | [`proc/path_other.go`](https://github.com/yetone/magpie/blob/4b5d6d725fae3d8a263f6e43c707400e3765b84f/internal/proc/path_other.go), [`proc/path_windows.go`](https://github.com/yetone/magpie/blob/4b5d6d725fae3d8a263f6e43c707400e3765b84f/internal/proc/path_windows.go), [`provider/install_windows.go`](https://github.com/yetone/magpie/blob/4b5d6d725fae3d8a263f6e43c707400e3765b84f/internal/provider/install_windows.go) | [`proc/path_other.go`](https://github.com/yetone/magpie/blob/9848a9062a65c49e074c09770dc7de73dd012bea/internal/proc/path_other.go), [`proc/path_windows.go`](https://github.com/yetone/magpie/blob/9848a9062a65c49e074c09770dc7de73dd012bea/internal/proc/path_windows.go), [`provider/install_windows.go`](https://github.com/yetone/magpie/blob/9848a9062a65c49e074c09770dc7de73dd012bea/internal/provider/install_windows.go): `LoginPath` and reuse of the moved registry reader |
| Upgrade destination | [`rtk_upgrade.go`](https://github.com/yetone/magpie/blob/4b5d6d725fae3d8a263f6e43c707400e3765b84f/internal/library/rtk_upgrade.go) | [`rtk_upgrade.go`](https://github.com/yetone/magpie/blob/9848a9062a65c49e074c09770dc7de73dd012bea/internal/library/rtk_upgrade.go): symlink-aware script destination |
| Entry points and presentation | Changed caller hunks in the pinned commit | [`internal/gui/library.go`](https://github.com/yetone/magpie/blob/9848a9062a65c49e074c09770dc7de73dd012bea/internal/gui/library.go), [`internal/gui/assets/library.js`](https://github.com/yetone/magpie/blob/9848a9062a65c49e074c09770dc7de73dd012bea/internal/gui/assets/library.js), [`library_cli.go`](https://github.com/yetone/magpie/blob/9848a9062a65c49e074c09770dc7de73dd012bea/library_cli.go): warning, explicit repair action and restart advice |

This is a bounded readset, not a complete consumer/runtime audit. In particular,
the change's description of Pi's extension is a reported motivation; the
extension's independent upstream implementation was not inspected here.

## Reconstruct the transition

**Task intent (commit report).** An agent could fail to find RTK by name although
Magpie found an installation and showed its hook enabled. The requested repair
was to expose that mismatch and offer an explicit PATH action, not silently
rewrite shell profiles or reinstall every agent.

**Before (inspected parent).** `rtkPath` first used Magpie's `exec.LookPath`, then
searched installer locations outside that PATH. `ReadRTK` exposed the discovered
path, version, gains and per-agent hook state. These facts did not answer whether
a separately launched agent could resolve the name `rtk`. On non-Windows,
`proc.UserPath` augmented Magpie's own environment with known installer folders
and login-shell entries. Thus the manager's search environment could be broader
than the consumer's. The parent view had no `OffPath` distinction.

**After (inspected change).** Discovery is retained, with Windows WinGet package
folders added. A separate `rtkReached` examines `proc.LoginPath`, and `ReadRTK`
adds `OffPath`, `PathDir` and `PathLink` when that check reports no match. The GUI
shows the warning whenever `OffPath` is true, but offers the repair button only
when a destination is available; the CLI also describes the applicable action.
`PathRTK` is reached by the explicit GUI
POST `/api/library/rtk/path` or CLI `magpie library rtk path`. It attempts the
platform-specific change, rereads the diagnostic view, rejects a still-off-PATH
result and lists enabled agents for restart. It does not restart those processes.

**Observed discrepancy, not a reconstructed agent failure.** The contrast is
between manager-side discovery/hook state and consumer-side name resolution.
No original coding-agent trajectory or independent agent patch is available in
this readset, so do not invent what an agent tried or why it made a mistake.

## Conditions and counter-signals

| Condition | What the pinned implementation establishes | What it does not establish |
| --- | --- | --- |
| Manager found a path | `rtkPath` found a manager-PATH match or an existing fallback path | Successful execution, consumer name resolution or matching consumer binary; fallback `exists` is only a stat check |
| Known consumer PATH, no runnable name | `rtkReached` found no non-directory `rtk`/`rtk.exe` in its nonempty entries; non-Windows also requires an execute bit | Exhaustive emulation of every shell's aliases, wrappers, launch environment or executable-resolution rules |
| Unknown consumer PATH | A nil `LoginPath` makes `rtkReached` return **true**, suppressing the warning | Confirmed reachability; absence of `OffPath` can mean unknown rather than success |
| Runnable same-name file found | The name/existence/mode predicate passed somewhere in the observed directories | Identity with `ReadRTK.Path`, matching version, first-resolved binary, integrity, hook compatibility or a successful launch; Windows does not apply a Unix execute-bit test |
| PATH repaired | The code rereads the view and gives restart advice | Changed environments of already-running agents/terminals or actual end-to-end RTK use |

Non-Windows `LoginPath` invokes the login shell interactively and caches a
successful PATH for a minute. Windows instead reads machine then user registry
PATH values, expanding variables and skipping unreadable keys. Neither is a
receipt from a specific agent process; caching, partial registry reads and
different launchers can weaken the approximation. A nil result is distinct from
a non-nil empty list in `rtkReached`.

### Mutation and diagnostic boundaries

- **Non-Windows repair:** select the first eligible directory from the fixed
  list of local-bin, user-bin, Homebrew, system-local-bin, Linuxbrew and Cargo
  locations. It must already occur in the observed PATH, be an existing writable
  directory and have no existing `rtk` entry under `Lstat`. Create a symlink to
  the discovered binary; do not overwrite an occupied entry or edit a profile.
  If no destination qualifies, return advice rather than invent another folder.
- **Windows repair:** use the binary's own directory, append it to the user's
  registry PATH if absent under the implemented case/trailing-separator check,
  update Magpie's process PATH and broadcast an environment-change notification.
  This is not the non-Windows symlink mechanism and not a copy of the binary.
- **Upgrade follow-through:** the non-Windows script-upgrade branch resolves a
  symlink's target directory rather than installing over the link. Existing
  package-manager branches remain separate; reading the proposed command does
  not execute an upgrade or prove installer classification for every layout.
- **Diagnostics are not pure read-only:** with a discovered binary, `ReadRTK`
  executes `--version` and `gain --daily --format json`. On the non-Windows
  off-PATH branch, selecting `PathDir` may create, close and attempt to remove a
  temporary file to probe writability; cleanup errors are not checked. PATH
  observation may execute login-shell profiles. Do not call this a harmless
  filesystem read or guarantee that an arbitrary discovered executable has no
  side effects. `ReadRTK` does not itself perform the explicit PATH repair.
- **Caller effects are separate:** the GUI GET handler can call `RTKLatest`,
  and the CLI calls `CheckLatest`; those paths may query GitHub. A read-labelled
  UI/CLI operation therefore is not an offline/no-execution guarantee either.

## Tests inspected, not executed

| Source at the change pin | Assertions inspected | Limit |
| --- | --- | --- |
| [`rtk_path_test.go`](https://github.com/yetone/magpie/blob/9848a9062a65c49e074c09770dc7de73dd012bea/internal/library/rtk_path_test.go), `TestRTKOffPath` | Fallback discovery outside PATH; no destination produces advice; an eligible user-bin destination produces a symlink and enabled-agent restart list; script-upgrade destination follows that link | `!windows`; fake RTK and test PATH, not a real agent/installer |
| [`library_test.go`](https://github.com/yetone/magpie/blob/9848a9062a65c49e074c09770dc7de73dd012bea/internal/library/library_test.go), sandbox helper; [`rtk_test.go`](https://github.com/yetone/magpie/blob/9848a9062a65c49e074c09770dc7de73dd012bea/internal/library/rtk_test.go) | Sandbox replaces `userPath` with the test's PATH; fake RTK supplies version/gain/install behavior | Does not exercise real login-shell discovery; fake output is not observed savings |
| [`rtk_upgrade_test.go`](https://github.com/yetone/magpie/blob/9848a9062a65c49e074c09770dc7de73dd012bea/internal/library/rtk_upgrade_test.go) | Fake Brew/script upgrades and a local fake latest-release server | Not real package-manager or Windows validation |
| [`library-rtk-path.test.cjs`](https://github.com/yetone/magpie/blob/9848a9062a65c49e074c09770dc7de73dd012bea/internal/gui/tests/library-rtk-path.test.cjs) | English/Chinese warning, enabled-agent tag, button POST, warning removal and restart message in Chromium/WebKit cases | API is mocked; does not run backend PATH mutation or an agent |

The inspected regression does not test unknown-PATH semantics, same-name binary
identity or Windows registry execution. This table describes test source, not a
passing test result. No upstream runtime or cross-platform qualification follows.

## Conditional lesson to reuse

When a manager configures a consumer with an absolute executable path but the
consumer's hooks later invoke it by name, **separate installation discovery,
hook enablement, consumer resolution and actual execution**. Inspect the actual
caller and environment at the target revision before reusing this lesson.

1. Identify the command shape and who resolves it. Record the manager's found
   path separately from the consumer environment; keep unknown observations
   unknown rather than upgrading a warning's absence to success.
2. Check name collisions and version/identity requirements separately. The
   historical predicate is evidence of its implementation, not a universal
   identity validator or a recommendation to fail open.
3. Before offering repair, identify authorized mutations, occupied destinations,
   platform behavior, upgrade destination and process-restart requirements.
   Classify diagnostic execution/probes separately from the explicit repair.
4. Use discriminating tests for the mismatch and the chosen mutation. Add
   unknown/identity/launcher/platform cases only under a separately accepted
   implementation scope; source inspection alone does not close those gaps.

This lesson is narrow: it does not apply unchanged when the consumer always
uses an absolute path, inherits a different verified environment or has another
resolver. The accepted historical patch is one contrastive solution, not the
unique correct repair or an enduring repository-wide convention.

## Evaluation and rights limits

The target diff and regression tests are learning inputs here. Reusing this
same transition as a heldout task would leak the answer; future efficacy work
needs independently separated tasks, frozen controls and correctness evidence.
InferRSI's existing `audit` and `kv-admission-diagnostic-v1` comparison adapters
handle report auditing/extraction and synthetic KV diagnosis respectively; they
do **not** provide a generic historical coding-task evaluator. Packaging and
Reader checks verify access/consistency, not this lesson's effect on agents.

This reference is an attributed interpretation of yetone/magpie, not a vendored
source snapshot. Its pinned [root LICENSE](https://github.com/yetone/magpie/blob/9848a9062a65c49e074c09770dc7de73dd012bea/LICENSE)
declares MIT; no substantial upstream code is reproduced here. That observation
does not resolve rights for other inherited sources, grant third-party/model
rights or alter existing unknown/absent license declarations in this skill.
