# External knowledge channels

`inferrsi find` can query knowledge that lives outside this repository. This page
explains what that is, why it is not installed with the package, and what to do
when you need it.

## A fresh install has no external channel

This is the **default and intended state**, not a missing installation step.

```bash
$ inferrsi find "CeilDivision 向上取整"
no_match    135 entries searched; rephrase, or search the corpus directly with rg

external (not locally verified; scores are not comparable across channels)
  cannbot-knowledge  [not_enabled]  cannbot knowledge is not enabled for this project
     fix: For Ascend tasks, install cannbot-knowledge if needed (checkout, Python environment and index), then enable it: inferrsi cannbot enable --checkout <path> --python <interpreter> --backend ascend --platform <platform>. Installation and verification: https://github.com/InferMatrixLab/InferRSI/blob/main/docs/external-channels.md#setting-one-up . For local-only search, use inferrsi find <query> --no-external.
```

`no_match` there is honest: the packaged corpus really holds nothing for that
query. The `not_enabled` line says an external source exists, was not approved
for this checkout, and how to approve it. Without that line a caller would
conclude the knowledge does not exist anywhere, which would be wrong.

On `main` `6c7e2379`, the packaged corpus holds **6 Ascend content cards and 0
per-API cards**. The external cannbot-knowledge corpus holds **10,550 cards,
2,993 of them Ascend C API cards**. Ignoring that gap is what the channel exists
to prevent.

## Ascend task preflight

When the user declares an Ascend task, check external knowledge availability
before researching optimization directions. Confirm the actual platform (`a2`,
`a3`, etc.); do not infer it from query text. If the task explicitly requires
local-only or knowledge-off operation, honor that condition and skip this probe.

1. From the target Git project, run `inferrsi cannbot describe` and inspect its
   JSON `state`. Exit code 0 alone does not establish that the channel is ready.
2. For `not_enabled`, proactively recommend cannbot-knowledge for Ascend API
   and operator references and provide the [installation guide](#setting-one-up)
   ([web link](https://github.com/InferMatrixLab/InferRSI/blob/main/docs/external-channels.md#setting-one-up)).
   Explain that the missing project grant does not prove the source is absent:
   an existing installation only needs project enablement. Offer
   `inferrsi find <query> --no-external` for local-only work.
3. For a missing checkout or reader (`unreachable`), use the same guide to
   restore the installation or enable its new location. For `index_stale`,
   rebuild the approved source's index using the returned guidance. Other
   failure states require their stated repair; do not report them as zero hits.
4. Apply existing installation/access authorization; if absent, obtain it before
   installing or enabling a source. Then complete all three
   [verification steps](#verify-the-installation) below before reporting that
   external knowledge is usable. If setup is deferred, continue with the
   permitted local knowledge and state that external coverage was unavailable.

`find --backend ascend` also emits the installation recommendation, enable
command and complete guide URL in text and JSON when the channel is not enabled,
whether or not local hits exist. Explicit `--no-external` and nonmatching
backends such as `cuda` omit this channel and its suggestion.

This integration uses a local checkout and reader process. Registering an MCP
server in an Agent host is not a prerequisite, and an installed host MCP does
not create an InferRSI project grant. InferRSI's `cannbot serve` proxy is not
implemented; the steps below configure the current CLI integration.

## Why it is not downloaded for you

cannbot-knowledge has its own CANN Open Software License Agreement v2.0.
InferRSI requires an explicitly approved local checkout and interpreter; it
does not clone, install or deploy that source automatically. Review the upstream
terms for your intended use before enabling it. Keeping the content outside the
package does not establish permission to use, transmit or redistribute it;
that organisational decision remains open in #476 Q1.

Nothing from an external checkout is ever copied into `src/inferrsi/knowledge/data/`,
a wheel, or `evidence/`.

## Setting one up

You supply a checkout, an interpreter, and the backend it serves. The `git`
executable must be available for read-time revision checks. Use Python 3.10+
and an interpreter with PyYAML. The following POSIX shell example uses `a2`;
replace it with the confirmed target platform. If the checkout, environment and
index already exist, reuse them and proceed to `enable` in the target Git project.

```bash
mkdir -p ~/src ~/venvs
git clone https://gitcode.com/cann/cannbot-knowledge.git ~/src/cannbot-knowledge
python3 -m venv ~/venvs/cannbot && ~/venvs/cannbot/bin/pip install pyyaml

# Build the search index once; the server refuses to answer a stale index.
~/venvs/cannbot/bin/python \
  ~/src/cannbot-knowledge/.agents/skills/knowledge-query/scripts/knowledge_index.py build

inferrsi cannbot enable \
  --checkout ~/src/cannbot-knowledge \
  --python ~/venvs/cannbot/bin/python \
  --backend ascend \
  --platform a2
```

`enable` proves the checkout answers before writing anything: it checks for
`.git`, the `knowledge/` bundle, the `knowledge-query` scripts and an executable
interpreter, then runs a real `discover`. A checkout that cannot answer is
refused rather than recorded, so a later search never fails for a reason you
already could have fixed.

| Flag | Meaning |
| --- | --- |
| `--checkout` | Git checkout containing `knowledge/` |
| `--python` | Interpreter with `pyyaml`, able to run the checkout's scripts |
| `--backend` | Default task backend; explicit `find --backend` takes precedence. Cannbot serves Ascend only. |
| `--platform` | Default upstream platform (`a2`, `a3`, `950`, `310p`, `910`, …) |

### Verify the installation

Run these checks from the same target Git project that was enabled. Choose a
platform supported by the task; the example below uses `a2`.

**1. Check discovery and configuration.**

```bash
$ inferrsi cannbot describe
{"state": "ok", "revision": "92dc2607...", "cards": 10550,
 "index": {"schema": "cannbot-knowledge-index.v1", "version": 3,
           "content_fingerprint": "75ef3269..."}, "platforms": ["a2"]}
```

Require `state: "ok"`, a source revision and the intended platform in
`platforms`. A successful `enable` or process exit alone is insufficient.

**2. Check integrated search.**

```bash
inferrsi find "CeilDivision" --backend ascend --platform a2 --external-limit 1 --json
```

Inspect the `cannbot-knowledge` entry in `external[]`: require `state: "ok"`,
its revision and at least one result with an `open` command. Local `no_match`
does not make this check fail. If the source answers with zero hits, discovery
worked but search-to-read verification is still incomplete; use a term known to
exist on the selected platform. A timeout or stale index needs repair first.

**3. Open the returned card with its identity.**

Run the exact `open` command returned by step 2. Its shape is:

```bash
inferrsi cannbot read <locator> --sha256 <card_sha256> --revision <revision>
```

Require `state: "ok"`, non-empty `text`, and a `card_sha256` and `revision`
matching the search result. If another page is needed, append `--page 2` to the
same command, preserving both identity flags. A drift rejection requires a new
search; do not drop the flags to make verification succeed. This verifies the
delivery path, not the card's technical claims or campaign evidence eligibility.
Do not copy the returned body into shared logs or evidence.

Revoke it with `inferrsi cannbot disable`. The grant lives at
`~/.config/inferrsi/cannbot-projects/<sha256(checkout)>.json` and is bound to the
project's `.git` identity, so copying it to another clone does not carry the
approval along.

## Using it

Once approved, the default path searches automatically because the grant declares
the backend:

```bash
inferrsi find "AscendC tiling 参数怎么算"
```

Or declare it per call:

```bash
inferrsi find "AscendC tiling 参数怎么算" --backend ascend --platform a2
inferrsi cannbot search "CeilDivision 向上取整" --platform a2 --limit 100
inferrsi cannbot read ops/ascendc/apis/utils_api/cpp_stdlib/math_functions/ceil_division
```

The generated `open` command includes `--revision <revision>` and
`--sha256 <card_sha256>`. Retain both with `--page 2` and later pages. A changed
checkout revision returns `version_mismatch`, even if the card bytes did not
change; changed bytes are rejected even if HEAD did not change. The worker
checks HEAD before and after reading, within the read timeout, and refuses an
observed revision change. This is a drift check on a mutable checkout, not an
atomic snapshot or a service for retrieving old versions. Every successful read
returns the observed checkout revision and digest of the full card bytes.
The upstream CLI uses `card_sha256` for a parsed metadata/body fingerprint;
this adapter preserves it as `source_card_sha256`. Before emitting a selected
hit, it verifies the source fingerprint using the approved checkout's parser
and computes `card_sha256` over those same raw bytes. It returns neither the
bytes nor private filesystem paths in search results.
A locator-only read returns the current card, revision and digest, without
promising continuity with an earlier search or page. A card digest does not validate its
cited resources or make it eligible as campaign evidence.

`find --platform` overrides the grant's upstream platform. If neither supplies
one, the channel reports `rejected` and gives the missing-platform guidance.
The default external result cap is 100 for cannbot; `--external-limit` overrides
it (1–200). These are returned hits, not the total number of upstream matches.

`--external-timeout` covers discovery and search together. Channels run
concurrently under that deadline. On timeout the caller cancels owned worker
processes and discards late results; subprocess teardown adds a short cleanup
interval. The cannbot adapter terminates its process group on POSIX; Windows
uses `taskkill /T /F` while the worker is alive. The new process-tree regression
runs on POSIX; Windows cleanup has not been qualified by that test. Generic
Python channel adapters must cooperate with the request deadline and register
owned resources; Python cannot forcibly stop arbitrary in-process threads.

### The backend gate

| Task backend | Channels searched |
| --- | --- |
| `ascend` | `cannbot-knowledge`, plus any platform-neutral channel |
| `cuda`, `mlx`, `rocm`, `cpu` | none — an Ascend source must not answer a CUDA task |
| not declared, no grant | none; cannbot reports `not_enabled` with setup guidance |

The backend is never inferred from the query text. A query containing "asc" is
not evidence that the task is an Ascend task, and a wrong inference would be
silent.

### Reading the result

```json
"external": [{
  "channel": "cannbot-knowledge", "state": "ok",
  "revision": "92dc2607...", "elapsed_ms": 1310,
  "score_scale": "knowledge-search.v5", "count": 3,
  "items": [{"locator": "ops/ascendc/apis/.../ceil_division", "score": 14.0,
             "status": "stable", "platforms": ["a2", "a3"],
             "card_sha256": "<raw-byte-sha256>",
             "source_card_sha256": "<upstream-card-fingerprint>",
             "open": "inferrsi cannbot read ops/... --sha256 <card_sha256> --revision <revision>"}]
}]
```

Three things to keep in mind:

**External hits are never in `items`.** They were not ranked on this corpus and
are not locally verified. A caller that only reads `items` therefore cannot
mistake them for validated knowledge.

**Scores are not comparable across channels.** `score_scale` names the system
that produced the number. The packaged corpus ranks 143 skills; upstream ranks
10,550 cards; the same word has a different idf in each. Merging them would mean
inventing a normalisation, so the columns stay separate.

**A state other than `ok` is not "no results".** `not_enabled`, `unreachable`,
`index_stale`, `timeout`, `version_mismatch`, `rejected` and `backend_unknown`
each mean the channel did not answer. Read `detail` and `fix`.

## Coverage measured

Six Ascend queries against a checkout at `92dc2607`, default cap 100. Local
counts are identical with and without the channel; only the external column
changes.

| Query | Local only | Local + external |
| --- | --- | --- |
| AscendC tiling 参数怎么计算 | 14 | 114 |
| CeilDivision 向上取整 | 0 | 100 |
| matmul 分块 性能 | 10 | 110 |
| 算子 精度 调试 溢出 | 75 | 175 |
| ACLGraph 图模式 捕获 | 100 | 200 |
| KV cache 显存 布局 | 128 | 228 |
| **Total** | **327** | **927** |

## Evidence and licensing

An external result is **not locally verified**. Cite it as
`cannbot-knowledge @ <revision>` and say so. It does not participate in a `PASS`
verdict.

When a receipt is added (not in this release), it will hold the locator, the
card's `card_sha256` and the index revision — never card text, never
`frontmatter`, never a `local_path`. A digest proves which card was cited without
redistributing it.

Whether CANN OSL v2.0 permits even a local read-only copy is an open question for
the organisation; see #476 Q1. This page documents the mechanism, not a legal
conclusion.

## What is not implemented

| Capability | State |
| --- | --- |
| `cannbot enable / disable / describe / search / read` | implemented |
| `find` integration with gating, budgets, per-channel states | implemented |
| MindIE as a second channel | not yet; `apps/mindie/` has the reader, not the adapter |
| `cannbot serve` (stdio MCP proxying `discover` / `search` / `read_card`) | not yet |
| `campaign import-cannbot` (receipts into evidence) | not yet |
| Automatic clone, index build or deployment | deliberately absent |
| In-memory discovery cache | deferred; discovery and search share the current call’s budget |

## Related

- [Operation guide](operations.md) — every entry point, effect class, boundary
- [#476](https://github.com/InferMatrixLab/InferRSI/issues/476) — access design and licence boundary
- [#388](https://github.com/InferMatrixLab/InferRSI/issues/388) — external dependency governance
- [Knowledge base](knowledge-base.md) — the packaged corpus this sits beside
